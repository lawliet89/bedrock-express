import json
from importlib import import_module
from os import getenv

from bedrock_client.bedrock.metrics.service import ModelMonitoringService
from fastapi import FastAPI, Request, Response

serve = import_module(getenv("BEDROCK_SERVER", "serve"))
ModelClass = getattr(serve, "Model")
pre_process = getattr(serve, "pre_process", lambda data, _: [float(x) for x in json.loads(data)])
post_process = getattr(serve, "post_process", None)

app = FastAPI()


@app.post("/")
async def predict(request: Request):
    # Using middleware causes tests to get stuck
    if not hasattr(request.app, "model"):
        request.app.model = ModelClass()
    if not hasattr(request.app, "monitor"):
        request.app.monitor = ModelMonitoringService()

    request_data = await request.body()
    request_form = await request.form()
    files = {k: v.file for k, v in request_form.items()}

    # User code to load features
    features = pre_process(request_data, files)

    # Compute the probability of the first class (True)
    score = request.app.model.predict(features)

    # Log before post_process to allow custom result type
    pid = request.app.monitor.log_prediction(
        request_body=request_data,
        features=features if hasattr(features, "__iter__") else [features],
        output=score[0] if isinstance(score, list) else score,
    )

    if post_process:
        score = post_process(score)

    return {"result": score, "prediction_id": pid}


@app.get("/metrics")
async def get_metrics(request: Request):
    """Returns real time feature values recorded by Prometheus
    """
    # Using middleware causes tests to get stuck
    if not hasattr(request.app, "model"):
        request.app.model = ModelClass()
    if not hasattr(request.app, "monitor"):
        request.app.monitor = ModelMonitoringService()

    body, content_type = request.app.monitor.export_http(
        params=dict(request.query_params), headers=request.headers,
    )
    return Response(body, media_type=content_type)
