from fastapi import Request


def get_service(request: Request, name: str):
    return request.app.state.services[name]
