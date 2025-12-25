# Data Service

Purpose
Local run
Build (Docker / Cloud Build)
Auth verification
Env
- Worker service that accepts job submissions and validates incoming JWTs.

Local run
- From the repository root run the application:
  - `python -m uvicorn app.main:application --reload --host 0.0.0.0 --port 8080`

Build (Docker / Cloud Build)
- Built by Cloud Build using `pyproject.toml` and `Dockerfile` at repository root.

Auth verification
- Validates bearer JWTs using `app.auth`. The expected audience for submit tokens is `https://worker.opteryx.app/api/v1/submit` and the expected issuer is `https://accounts.google.com`.

Env
- `PORT` — service port (default `8080`).

## API Overview

End Point            | GET | POST | PATCH | DELETE
-------------------- | --- | ---- | ----- | ------
/health              | Read Service Health | - | - | -
/api/v1/submit      | -   | Submit Job (202) | - | -

## Request Fulfillment

**I want to check service health**

    [GET]       /health

**I want to submit a job for processing**

    [POST]      /api/v1/submit

## Definitions

### Submit Job

#### Request

~~~
[POST] https://worker.opteryx.app/api/v1/submit
~~~

*JSON Body*

~~~json
{
    "execution_id": "string"
}
~~~

Name | Type | Optional | Notes
---- | ---- | ---- | ----
execution_id | string | no | Unique identifier for the submitted job

*Query Parameters*

This endpoint does not require query parameters; authentication is via a Bearer JWT in the `Authorization` header.

#### Response

*JSON Body* (typical)

~~~json
{
    "accepted": true,
    "job": "<execution_id>",
    "jwt_sub": "<subject>"
}
~~~

Name | Type | Optional | Notes
---- | ---- | ---- | ----
accepted | boolean | no | Indicates the job was accepted for processing
job | string | no | The `execution_id` provided in the request
jwt_sub | string | yes | Subject claim from the validated JWT

*Response Codes*

200 - OK (synchronous success through middleware)
202 - Accepted (handler-declared accepted status)
401 - Unauthorized (missing/invalid JWT)
500 - Internal Server Error

### Health Check

#### Request

~~~
[GET] https://worker.opteryx.app/health
~~~

#### Response

*JSON Body*

~~~json
{
    "status": "ok"
}
~~~

*Response Codes*

200 - OK

---

This README section documents the primary HTTP endpoints exposed by this service. For implementation details see the route definitions in the codebase (`app/routes`).
