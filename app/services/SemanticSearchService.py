import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
import logging
import time
import urllib.request
import urllib.error
import os
from typing import Optional, List, Dict, Any, Union

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SemanticSearchService:
    """
    Serviço de busca semântica que mantém conexão com ChromaDB
    e modelo Hugging Face carregado. 
    Singleton por worker para otimizar carregamento.
    """

    def __init__(self, model_name='paraphrase-multilingual-mpnet-base-v2'):
        
        self.chroma_host = os.environ.get('CHROMA_HOST', 'chromadb')
        self.chroma_port = os.environ.get('CHROMA_PORT', '8000')
        self.chroma_url = f"http://{self.chroma_host}:{self.chroma_port}"
        
        self.model_name = model_name
        self.collection_cache = {}
        self._chroma_client = None

        logger.info("--- A carregar o modelo de IA Hugging Face... Isto pode demorar. ---")
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
        self.model = self.embedding_function.models[model_name]
        logger.info("--- Modelo carregado com sucesso! ---")

    def _wait_for_chroma(self, retries: int = 15, delay: int = 2):
        """Espera o serviço ChromaDB ficar disponível."""
        logger.info(f"--- A aguardar pelo ChromaDB em {self.chroma_url}... ---")
        for i in range(retries):
            try:
                with urllib.request.urlopen(f"{self.chroma_url}/api/v1/heartbeat", timeout=5) as response:
                    if response.status == 200:
                        logger.info("--- ChromaDB está pronto! ---")
                        return True
            except Exception:
                pass
            logger.info(f"--- Tentativa {i+1}/{retries}. Aguardando {delay}s... ---")
            time.sleep(delay)
        raise RuntimeError(f"Não foi possível conectar ao ChromaDB em {self.chroma_url} após {retries} tentativas.")

    def _connect(self):
        """Conecta ao ChromaDB se ainda não estiver conectado."""
        if self._chroma_client is None:
            self._wait_for_chroma()
            try:
                settings = Settings(
                    chroma_api_impl="chromadb.api.fastapi.FastAPI",
                    chroma_server_host=self.chroma_host,
                    chroma_server_http_port=self.chroma_port
                )
                self._chroma_client = chromadb.Client(settings=settings)
                logger.info("--- ChromaDB conectado com sucesso! ---")
            except Exception as e:
                logger.error(f"Falha ao conectar: {str(e)}")
                raise RuntimeError(f"Não foi possível conectar ao ChromaDB. Erro: {e}")

    @property
    def chroma_client(self):
        """Garante que o chroma_client exista antes do uso."""
        if self._chroma_client is None:
            self._connect()
        return self._chroma_client

    def get_collection(self, collection_name: str):
        """Retorna a coleção, criando se necessário e usando cache por worker."""
        if collection_name not in self.collection_cache:
            
            collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"} 
            )
            
            self.collection_cache[collection_name] = collection
        return self.collection_cache[collection_name]

    def setup_collection(self, collection_name: str, documents: list[str]):
        """Cria uma coleção e adiciona documentos iniciais, se necessário."""
        collection = self.get_collection(collection_name)
        if collection.count() == 0 and documents:
            logger.info(f"A adicionar {len(documents)} documentos à coleção '{collection_name}'...")
            collection.add(
                documents=documents,
                ids=[f"doc_{i}" for i in range(len(documents))]
            )
            logger.info(f"--- {len(documents)} documentos adicionados. ---")
        else:
            logger.info(f"--- Coleção '{collection_name}' já contém {collection.count()} documentos. ---")

    def search(self, 
               query: str, 
               video_id_filter: Optional[Union[str, List[str]]] = None, 
               num_results: int = 10,
               threshold: float = 0.6
               ) -> List[Dict[str, Any]]:
        """
        Busca semanticamente na coleção, com filtro opcional e threshold de relevância.
        'video_id_filter' pode ser um único youtube_id (str) ou uma lista de ids.
        """
        collection_name = "comentarios_produtos"
        collection = self.get_collection(collection_name)
        
        query_params = {
            "query_texts": [query],
            "n_results": num_results,
            "include": ["documents", "distances", "metadatas"]
        }
        
        if isinstance(video_id_filter, list):
            if len(video_id_filter) == 1:
                query_params["where"] = {"video_id": video_id_filter[0]}
                logger.info(f"--- Buscando: '{query}' (FILTRADO para youtube_id: {video_id_filter[0]}) ---")
            elif video_id_filter:
                query_params["where"] = {"video_id": {"$in": video_id_filter}}
                logger.info(f"--- Buscando: '{query}' (FILTRADO para {len(video_id_filter)} videos) ---")
        elif video_id_filter:
            query_params["where"] = {"video_id": video_id_filter}
            logger.info(f"--- Buscando: '{query}' (FILTRADO para youtube_id: {video_id_filter}) ---")
        else:
            logger.info(f"--- Buscando: '{query}' (em TODOS os vídeos, Top {num_results} candidatos) ---")

        results = collection.query(**query_params)
        
        final_results = []
        if not results['documents']:
            return []

        for doc, dist, meta in zip(results['documents'][0], results['distances'][0], results['metadatas'][0]):
            
            if dist <= threshold: 
                final_results.append({
                    "documento": doc,
                    "distancia": dist,
                    "metadados": meta
                })
        
        logger.info(f"--- Encontrados {len(final_results)} resultados relevantes (limite: {threshold}) ---")
        
        return final_results