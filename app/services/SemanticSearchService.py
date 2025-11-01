import chromadb
from sentence_transformers import SentenceTransformer

class SemanticSearchService:
    def __init__(self, model_name='paraphrase-multilingual-mpnet-base-v2'):
        
        print("--- A carregar o modelo de IA Hugging Face... Isto pode demorar alguns minutos. ---")
        self.model = SentenceTransformer(model_name)
        print("--- Modelo carregado com sucesso! ---")
        
        self.chroma_client = chromadb.Client()
        self.collection = None

    def setup_collection(self, collection_name: str, documents: list[str]):

        print(f"--- A configurar a coleção '{collection_name}' no ChromaDB... ---")
        self.collection = self.chroma_client.create_collection(name=collection_name)
        
        embeddings = self.model.encode(documents)
        
        self.collection.add(
            embeddings=embeddings.tolist(),
            documents=documents,
            ids=[f"doc_{i}" for i in range(len(documents))]
        )
        print(f"--- Foram adicionados {len(documents)} documentos à coleção. ---")

    def search(self, query: str, num_results: int = 2) -> list[str]:

        if not self.collection:
            raise RuntimeError("A coleção não foi configurada. Chame 'setup_collection' primeiro.")
            
        print(f"--- A realizar a busca para a pergunta: '{query}' ---")
        query_embedding = self.model.encode([query])
        
        results = self.collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=num_results
        )
        
        return results['documents'][0] if results and 'documents' in results and results['documents'] else []
