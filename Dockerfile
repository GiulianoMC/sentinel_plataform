# Usar uma imagem oficial do Python como base
FROM python:3.9-slim

# Definir o diretório de trabalho dentro do contêiner
WORKDIR /code

# Copiar o arquivo de dependências para o contêiner
COPY ./requirements.txt /code/requirements.txt

# Instalar as dependências
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copiar o código da aplicação para o contêiner
COPY ./app /code/app

# Comando para executar a aplicação quando o contêiner iniciar
# Uvicorn é o servidor ASGI que o FastAPI usa
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]