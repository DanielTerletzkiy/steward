"""Domain logic. Routes and the WebSocket API are thin wrappers around these functions."""


class ServiceError(Exception):
    """Base for errors that map to a 4xx response."""

    status = 400


class NotFound(ServiceError):
    status = 404


class Invalid(ServiceError):
    status = 400
