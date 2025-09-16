from fastapi import status
from fastapi.exceptions import HTTPException

class QuizError(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)

    @classmethod
    def server_error(cls, detail: str):
        return cls(detail=detail, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    @classmethod
    def validation_error(cls, detail: str):
        return cls(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
        
    @classmethod
    def not_found(cls, detail: str):
        return cls(detail=detail, status_code=status.HTTP_404_NOT_FOUND)
        
    @classmethod
    def conflict(cls, detail: str):
        return cls(detail=detail, status_code=status.HTTP_409_CONFLICT)
