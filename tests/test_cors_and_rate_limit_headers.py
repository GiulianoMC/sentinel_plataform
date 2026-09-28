"""O front lê Retry-After para o countdown; sem expose_headers o browser não o enxerga."""


def test_cors_expoe_retry_after(client, auth_headers, test_video):
    response = client.get(
        f"/analytics/{test_video.youtube_id}/summary",
        headers={**auth_headers, "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    expostos = response.headers["access-control-expose-headers"]
    assert "Retry-After" in expostos


def test_preflight_permite_authorization(client):
    response = client.options(
        "/insights/qualquer/ask",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_429_traz_retry_after(client):
    """O limite de /auth/register é 5/minute: o 6º pedido devolve 429 com a janela."""
    for i in range(5):
        client.post("/auth/register",
                    json={"email": f"rl{i}@example.com", "password": "senha123"})

    response = client.post("/auth/register",
                           json={"email": "rl6@example.com", "password": "senha123"})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_ask_rate_limit_do_endpoint(client, auth_headers, db_session, test_user):
    """O /ask tem limite próprio de 10/min (cota do LLM é partilhada com o worker_ai)."""
    from app.models.VideoModel import Video

    db_session.add(Video(youtube_id="rl_video", titulo="RL", user_id=test_user.id))
    db_session.commit()

    corpo = {"question": "Faça um resumo dos comentários", "strategy": "sample"}
    for _ in range(10):
        assert client.post("/insights/rl_video/ask", headers=auth_headers, json=corpo).status_code != 429

    excedido = client.post("/insights/rl_video/ask", headers=auth_headers, json=corpo)
    assert excedido.status_code == 429
    assert excedido.headers["Retry-After"] == "60"
