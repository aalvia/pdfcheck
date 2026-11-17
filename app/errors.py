"""Errores de negocio que la API convierte en respuestas HTTP claras."""


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class UploadRejected(ApiError):
    """El archivo ni siquiera entra al flujo: no es un PDF usable."""

    def __init__(self, message: str, code: str = "invalid_file"):
        super().__init__(400, code, message)


class AIExtractionError(ApiError):
    """La IA configurada no pudo usarse. No autoriza a inventar datos."""

    def __init__(self, message: str):
        super().__init__(503, "ai_unavailable", message)
