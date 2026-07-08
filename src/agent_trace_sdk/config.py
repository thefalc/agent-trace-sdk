from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .exceptions import ConfigError


@dataclass(frozen=True)
class KafkaConfig:
    bootstrap_servers: str
    security_protocol: str = "SASL_SSL"
    sasl_mechanisms: str = "PLAIN"
    sasl_username: str = ""
    sasl_password: str = ""

    def to_confluent_config(self) -> dict[str, str]:
        config: dict[str, str] = {
            "bootstrap.servers": self.bootstrap_servers,
            "security.protocol": self.security_protocol,
            "sasl.mechanisms": self.sasl_mechanisms,
        }
        if self.sasl_username:
            config["sasl.username"] = self.sasl_username
            config["sasl.password"] = self.sasl_password
        return config

    @classmethod
    def from_env(cls, dotenv_path: str | None = None) -> KafkaConfig:
        load_dotenv(dotenv_path)
        bootstrap = os.environ.get("CONFLUENT_BOOTSTRAP_SERVERS")
        if not bootstrap:
            raise ConfigError("CONFLUENT_BOOTSTRAP_SERVERS environment variable is required")
        return cls(
            bootstrap_servers=bootstrap,
            security_protocol=os.environ.get("CONFLUENT_SECURITY_PROTOCOL", "SASL_SSL"),
            sasl_mechanisms=os.environ.get("CONFLUENT_SASL_MECHANISMS", "PLAIN"),
            sasl_username=os.environ.get("CONFLUENT_API_KEY", ""),
            sasl_password=os.environ.get("CONFLUENT_API_SECRET", ""),
        )


@dataclass(frozen=True)
class SchemaRegistryConfig:
    url: str
    api_key: str = ""
    api_secret: str = ""

    def to_confluent_config(self) -> dict[str, str]:
        config: dict[str, str] = {"url": self.url}
        if self.api_key:
            config["basic.auth.user.info"] = f"{self.api_key}:{self.api_secret}"
        return config

    @classmethod
    def from_env(cls, dotenv_path: str | None = None) -> SchemaRegistryConfig:
        load_dotenv(dotenv_path)
        url = os.environ.get("CONFLUENT_SCHEMA_REGISTRY_URL")
        if not url:
            raise ConfigError("CONFLUENT_SCHEMA_REGISTRY_URL environment variable is required")
        return cls(
            url=url,
            api_key=os.environ.get("CONFLUENT_SCHEMA_REGISTRY_API_KEY", ""),
            api_secret=os.environ.get("CONFLUENT_SCHEMA_REGISTRY_API_SECRET", ""),
        )
