__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

from sentence_transformers import SentenceTransformer
import chromadb

def executar_prova_de_conceito():
    """
    Função principal que demonstra a busca semântica.
    """
    print("--- Iniciando a Prova de Conceito da Busca Semântica ---")

    print("Passo 1: Carregando o modelo de IA (isso pode demorar um pouco na primeira vez)...")
    model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
    print("Modelo carregado com sucesso!")

    comentarios = [
        "A bateria deste telemóvel dura imenso, recomendo vivamente!",
        "O ecrã tem uma qualidade de imagem incrível, as cores são muito vivas.",
        "Qual é o período de garantia para este produto?",
        "O custo do frete para a minha região está demasiado alto.",
        "A autonomia da bateria é realmente um grande diferencial neste aparelho.",
        "A câmara tira fotografias fantásticas, mesmo com pouca luz."
    ]
    print("\nPasso 2: Utilizando os seguintes comentários como base de dados:")
    for c in comentarios:
        print(f"- {c}")

    print("\nPasso 3: Convertendo os comentários em vetores semânticos...")
    embeddings = model.encode(comentarios)
    print(f"Foram gerados {len(embeddings)} vetores.")

    print("\nPasso 4: Configurando o ChromaDB e adicionando os vetores...")
    client = chromadb.Client()
    collection = client.create_collection("teste_comentarios")
    
    collection.add(
        embeddings=embeddings.tolist(),
        documents=comentarios,
        ids=[f"id_{i}" for i in range(len(comentarios))]
    )
    print("Dados adicionados à coleção do ChromaDB.")

    pergunta = "Estou preocupado com a duração da bateria, o que dizem sobre isso?"
    print(f"\nPasso 5: Realizando a busca semântica para a pergunta: '{pergunta}'")

    embedding_pergunta = model.encode([pergunta])[0]

    resultados = collection.query(
        query_embeddings=[embedding_pergunta.tolist()],
        n_results=2
    )

    print("\n--- RESULTADO DA BUSCA ---")
    print("Os 2 comentários mais relevantes encontrados foram:")
    for doc in resultados['documents'][0]:
        print(f"-> \"{doc}\"")

if __name__ == "__main__":
    executar_prova_de_conceito()