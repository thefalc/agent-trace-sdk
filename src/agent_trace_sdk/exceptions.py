class TracerError(Exception):
    pass


class ProducerError(TracerError):
    pass


class ConfigError(TracerError):
    pass
