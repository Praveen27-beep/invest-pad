"""Pydantic request/response DTOs for the routers.

Money fields are typed ``str`` and rate/ratio fields ``float``, matching the boundary
rule in ``app/database.py``'s ``money()``/``rate()`` and ``schema/*.schema.json``'s
``$defs/decimal`` -- a Decimal crosses the JSON boundary as a string, a ratio as a
number. These schemas describe that boundary; they do not change it.
"""
