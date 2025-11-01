import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SemanticSearchService:
    def __init__(self, model_name='paraphrase-multilingual-mpnet-base-v2'):
        
        logger.info("--- A carregar o modelo de IA Hugging Face... Isto pode demorar. ---")
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
        self.model = self.embedding_function.models[model_name]
        logger.info("--- Modelo carregado com sucesso! ---")
        
        self.chroma_client = chromadb.HttpClient(host='chromadb', port=8000)
        
        self.collection = None

    def setup_collection(self, collection_name: str, documents: list[str]):

        logger.info(f"--- A configurar a coleção '{collection_name}' no ChromaDB... ---")
        
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function 
        )
        
        if self.collection.count() == 0 and documents:
            logger.info(f"Coleção vazia. A adicionar {len(documents)} documentos base...")
            self.collection.add(
                documents=documents,
                ids=[f"doc_{i}" for i in range(len(documents))]
            )
            logger.info(f"--- Foram adicionados {len(documents)} documentos à coleção. ---")
        else:
            logger.info(f"--- Coleção '{collection_name}' já existe e contém {self.collection.count()} documentos. ---")

    def search(self, query: str, num_results: int = 2) -> list[str]:

        if not self.collection:
            try:
                self.collection = self.chroma_client.get_collection(name="comentarios_produtos")
            except Exception as e:
                logger.error(f"Falha ao obter coleção: {e}")
                raise RuntimeError("A coleção não foi configurada ou não existe.")
                
        logger.info(f"--- A realizar a busca para a pergunta: '{query}' ---")
        
        results = self.collection.query(
            query_texts=[query],
            n_results=num_results
        )
        
        return results['documents'][0] if results and 'documents' in results and results['documents'] else []