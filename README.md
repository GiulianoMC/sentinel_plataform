Plataforma Sentinela<br>
Este é o repositório do projeto "Plataforma Sentinela", um Trabalho de Conclusão de Curso (TCC) do curso de Engenharia da Computação.

O projeto consiste na construção de uma plataforma de engenharia de dados para analisar, em larga escala, o conteúdo textual gerado por utilizadores (como comentários do YouTube) utilizando técnicas de busca semântica com Inteligência Artificial.

🚀 Tecnologias Utilizadas
Linguagem: Python 3.9

Framework da API: FastAPI

Inteligência Artificial: Sentence-Transformers

Base de Dados Vetorial: ChromaDB

Base de Dados Relacional: PostgreSQL

Processamento Assíncrono: Celery & RabbitMQ

Ambiente: Docker & Docker Compose

🛠️ Como Executar o Projeto
Certifique-se de que tem o Git, Docker e Docker Compose instalados na sua máquina.

Clonar o repositório:

git clone https://github.com/GiulianoMC/sentinel_plataform.git

Navegar para a pasta do projeto:

cd sentinel_platform

Construir e iniciar os contentores:

docker-compose up --build

Verificar a execução:

A API estará disponível em: http://localhost:8000

A documentação interativa da API estará disponível em: http://localhost:8000/docs

Este projeto está em desenvolvimento.

