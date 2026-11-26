"""Mensageria comum dos serviços UniRide: outbox, publicador (relay) e consumidor idempotente.

Este arquivo é a fonte única; `scripts/sync-shared.sh` copia-o para `app/mensageria.py`
de cada serviço (cada imagem Docker continua independente, com contexto de build próprio).
Não edite as cópias: edite este arquivo e rode o script.

Seção 4.5 da arquitetura:
  * o serviço grava a alteração e o evento NA MESMA transação local (tabela outbox_event);
  * o publicador lê os eventos pendentes e publica no Kafka com chave = aggregate_id;
  * o consumidor registra (message_id, consumer) em inbox_message na mesma transação
    do efeito, descartando mensagens repetidas (entrega at-least-once).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Iterable

log = logging.getLogger("mensageria")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Catálogo de tópicos (seção 4.1, "Catálogo de eventos").
TOPICOS = [
    "usuarios.eventos",
    "caronas.eventos",
    "solicitacoes.eventos",
    "viagens.eventos",
    "avaliacoes-rateio.eventos",
    "caronas.comandos",
    "avaliacoes-rateio.comandos",
]

OUTBOX_INBOX_DDL = """
CREATE TABLE IF NOT EXISTS outbox_event (
  id            UUID PRIMARY KEY,
  aggregate     VARCHAR(60) NOT NULL,
  aggregate_id  VARCHAR(60) NOT NULL,
  event_type    VARCHAR(80) NOT NULL,
  topic         VARCHAR(80) NOT NULL,
  payload       JSONB       NOT NULL,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_event (occurred_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS inbox_message (
  message_id    UUID        NOT NULL,
  consumer      VARCHAR(60) NOT NULL,
  processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (message_id, consumer)
);
"""


def agora() -> datetime:
    return datetime.now(timezone.utc)


def configurar_log() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


# --------------------------------------------------------------------------- PostgreSQL

def conectar():
    """Conexão nova com linhas como dict. Use `with conectar() as conn:` (commit no fim)."""
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def preparar_banco(ddl: str, tentativas: int = 60) -> None:
    """Espera o banco do serviço e roda as migrações dele (DDL idempotente) + outbox/inbox."""
    for i in range(tentativas):
        try:
            with conectar() as conn:
                conn.execute(ddl)
                conn.execute(OUTBOX_INBOX_DDL)
            log.info("banco pronto")
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("banco indisponível (%s/%s): %s", i + 1, tentativas, exc)
            time.sleep(2)
    raise RuntimeError("banco não ficou disponível")


def envelope(event_type: str, aggregate_id: str, data: dict, *,
             aggregate_version: int = 1, correlation_id: str | None = None) -> dict:
    """Envelope padrão dos eventos e comandos (seção 4.5)."""
    return {
        "eventId": str(uuid.uuid4()),
        "eventType": event_type,
        "schemaVersion": 1,
        "aggregateId": str(aggregate_id),
        "aggregateVersion": aggregate_version,
        "occurredAt": agora().isoformat(),
        "correlationId": correlation_id or str(uuid.uuid4()),
        "data": data,
    }


def gravar_outbox(cur, *, topic: str, aggregate: str, aggregate_id: str, event_type: str,
                  data: dict, key: str | None = None, aggregate_version: int = 1,
                  correlation_id: str | None = None) -> dict:
    """Grava o evento na outbox usando o cursor da transação de negócio em andamento.

    `key` é a chave de partição no Kafka (padrão: aggregate_id). Comandos da SAGA usam o
    sagaId como chave para que ReservarVaga e LiberarVaga da mesma SAGA fiquem em ordem.
    """
    from psycopg.types.json import Jsonb

    env = envelope(event_type, aggregate_id, data,
                   aggregate_version=aggregate_version, correlation_id=correlation_id)
    env["_key"] = str(key or aggregate_id)
    cur.execute(
        "INSERT INTO outbox_event (id, aggregate, aggregate_id, event_type, topic, payload) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (env["eventId"], aggregate, str(aggregate_id), event_type, topic, Jsonb(env)),
    )
    log.info("outbox <- %s %s (%s)", topic, event_type, aggregate_id)
    return env


def ja_processado(cur, message_id: str, consumer: str) -> bool:
    """Registra a mensagem na inbox. True se ela já tinha sido processada (descartar)."""
    cur.execute(
        "INSERT INTO inbox_message (message_id, consumer) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (message_id, consumer),
    )
    return cur.rowcount == 0


# --------------------------------------------------------------------------- Kafka

def criar_topicos(topicos: Iterable[str] = TOPICOS) -> None:
    """Cria os tópicos (3 partições). Ignora os que já existem."""
    from confluent_kafka.admin import AdminClient, NewTopic

    for i in range(60):
        try:
            admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
            existentes = set(admin.list_topics(timeout=5).topics)
            novos = [NewTopic(t, num_partitions=3, replication_factor=1)
                     for t in topicos if t not in existentes]
            for t, fut in admin.create_topics(novos).items() if novos else []:
                try:
                    fut.result()
                    log.info("tópico criado: %s", t)
                except Exception as exc:  # noqa: BLE001 - já existe (corrida entre serviços)
                    log.debug("tópico %s: %s", t, exc)
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("kafka indisponível (%s/60): %s", i + 1, exc)
            time.sleep(2)


class PublicadorOutbox(threading.Thread):
    """Relay da outbox: publica no Kafka os eventos com published_at nulo, em ordem."""

    def __init__(self, intervalo: float = 0.3):
        super().__init__(daemon=True, name="publicador-outbox")
        self.intervalo = intervalo

    def run(self) -> None:
        from confluent_kafka import Producer

        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
                             "enable.idempotence": True, "acks": "all"})
        while True:
            try:
                self._ciclo(producer)
            except Exception as exc:  # noqa: BLE001
                log.warning("publicador: %s", exc)
                time.sleep(2)
            time.sleep(self.intervalo)

    def _ciclo(self, producer) -> None:
        with conectar() as conn, conn.cursor() as cur:
            # Uma instância ativa por serviço (advisory lock da transação).
            cur.execute("SELECT pg_try_advisory_xact_lock(hashtext('outbox-relay')) AS ok")
            if not cur.fetchone()["ok"]:
                return
            cur.execute(
                "SELECT id, topic, payload FROM outbox_event WHERE published_at IS NULL "
                "ORDER BY occurred_at LIMIT 200"
            )
            pendentes = cur.fetchall()
            if not pendentes:
                return
            falhas: list = []
            for ev in pendentes:
                payload = dict(ev["payload"])
                key = payload.pop("_key", payload.get("aggregateId"))
                producer.produce(
                    ev["topic"], key=key, value=json.dumps(payload, default=str),
                    on_delivery=lambda err, _msg: falhas.append(err) if err else None,
                )
            producer.flush(10)
            if falhas:
                # Não marca nada: o lote inteiro sai de novo (consumidores desduplicam).
                raise RuntimeError(f"falha ao publicar: {falhas[0]}")
            cur.execute(
                "UPDATE outbox_event SET published_at = now() WHERE id = ANY(%s)",
                ([ev["id"] for ev in pendentes],),
            )
            for ev in pendentes:
                log.info("kafka -> %s %s", ev["topic"], ev["payload"].get("eventType"))


class ConsumidorKafka(threading.Thread):
    """Consome tópicos e chama `handler(envelope, topico)`.

    O offset só é confirmado depois que o handler termina (at-least-once). O handler deve
    ser idempotente: nos serviços com PostgreSQL ele usa `ja_processado` na mesma transação.
    """

    def __init__(self, group_id: str, topicos: list[str], handler: Callable[[dict, str], None]):
        super().__init__(daemon=True, name=f"consumidor-{group_id}")
        self.group_id = group_id
        self.topicos = topicos
        self.handler = handler

    def run(self) -> None:
        from confluent_kafka import Consumer

        while True:
            try:
                consumer = Consumer({
                    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
                    "group.id": self.group_id,
                    "enable.auto.commit": False,
                    "auto.offset.reset": "earliest",
                    # Membro estático: o container que reinicia com o mesmo hostname reassume as
                    # partições na hora, sem esperar a sessão do consumidor antigo expirar
                    # (padrão 45 s, maior que o timeout da SAGA). Réplicas têm hostnames distintos.
                    "group.instance.id": f"{self.group_id}-{socket.gethostname()}",
                    "session.timeout.ms": 10000,
                    "heartbeat.interval.ms": 3000,
                })
                consumer.subscribe(self.topicos)
                log.info("consumidor %s inscrito em %s", self.group_id, self.topicos)
                self._loop(consumer)
            except Exception as exc:  # noqa: BLE001
                log.warning("consumidor %s reiniciando: %s", self.group_id, exc)
                time.sleep(2)

    def _loop(self, consumer) -> None:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                log.debug("kafka: %s", msg.error())
                continue
            try:
                env = json.loads(msg.value())
            except ValueError:
                log.error("mensagem inválida descartada em %s", msg.topic())
                consumer.commit(message=msg, asynchronous=False)
                continue
            for tentativa in range(1, 6):
                try:
                    self.handler(env, msg.topic())
                    break
                except Exception as exc:  # noqa: BLE001
                    log.warning("handler %s falhou (%s/5) em %s: %s",
                                self.group_id, tentativa, env.get("eventType"), exc)
                    time.sleep(min(2 ** tentativa, 10))
            consumer.commit(message=msg, asynchronous=False)
