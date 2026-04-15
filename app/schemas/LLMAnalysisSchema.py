from pydantic import BaseModel, Field
from typing import Optional

class CommentAnalysisResponse(BaseModel):
    sentiment: int = Field(
        ..., 
        description="Classificação do sentimento do comentário de 1 a 5, onde 1 é muito negativo e 5 é muito positivo."
    )
    intent: str = Field(
        ..., 
        description="A intenção principal do comentário. Escolha uma destas: 'Duvida', 'Intencao_Compra', 'Feedback_Uso', 'Comparacao', 'Critica', 'Outro'."
    )
    product_mentioned: Optional[str] = Field(
        None, 
        description="Nome do produto mencionado no comentário. Se nenhum for mencionado, retorne null."
    )