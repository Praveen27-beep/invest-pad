"""The four adapter registries must agree with each other.

Adding an adapter means touching several dicts that live in two modules and know nothing
about one another:

- ``file_validation.ROUTING``   document kind -> (adapter name, owning route)
- ``file_validation.LABELS``    document kind -> the name a person reads
- ``routers.ingest._DOCTYPES``  adapter name -> (doctype, content_type)
- ``routers.ingest._build_adapter``  adapter name -> an instance

The failure this file exists to prevent is specific and silent at review time:
``_DOCTYPES[verdict.adapter]`` in ``ingest_files`` is indexed **unguarded**, so an adapter
registered in ROUTING but forgotten in _DOCTYPES raises ``KeyError`` mid-upload and the
person uploading gets a 500 with no hint. Everything else in that loop degrades politely;
this one line does not.

Cheap to run, and it fails at the moment the registries diverge rather than the first
time somebody uploads the relevant file.
"""

from __future__ import annotations

from app.ingest import file_validation
from app.routers.ingest import _DOCTYPES, _build_adapter


def test_every_routed_adapter_has_a_doctype() -> None:
    """The KeyError guard. ``_DOCTYPES[verdict.adapter]`` is unguarded by design -- a
    missing entry is a programming error, not a user error -- so this is where it gets
    caught."""
    routed = {adapter for adapter, _route in file_validation.ROUTING.values()}
    assert routed <= set(_DOCTYPES), (
        f"in ROUTING but not _DOCTYPES: {sorted(routed - set(_DOCTYPES))} -- "
        "ingest_files would raise KeyError on this file kind"
    )


def test_every_routed_adapter_can_actually_be_built() -> None:
    """_build_adapter raises HTTPException(422) for an unknown name. A name that routes
    but cannot be constructed turns every upload of that kind into a 422 that blames the
    file rather than the registry."""
    for document, (adapter, _route) in sorted(file_validation.ROUTING.items()):
        instance = _build_adapter(adapter)
        assert instance.name == adapter, (
            f"{document}: ROUTING says {adapter!r} but the built instance calls itself "
            f"{instance.name!r} -- reparse_batch rebuilds by name and would diverge"
        )


def test_every_doctype_entry_is_reachable() -> None:
    """The other direction: an adapter with a doctype but no route is dead configuration,
    unless a route hands it the name directly (the declared-adapter endpoints do)."""
    from app.ingest.llm_adapter import LlmDocumentAdapter
    from app.routers.ingest import _CSV_ADAPTERS, _PDF_ADAPTERS, _XLSX_ADAPTERS

    declarable = set(_CSV_ADAPTERS) | set(_XLSX_ADAPTERS) | set(_PDF_ADAPTERS)
    routed = {adapter for adapter, _route in file_validation.ROUTING.values()}
    # The third reachability path, and the only member of it. LlmDocumentAdapter is
    # deliberately absent from ROUTING: classification stays deterministic and the model
    # never decides what a document is. It is reached from ingest_files' `not verdict.ok`
    # branch instead -- the files no deterministic parser claimed.
    fallback = {LlmDocumentAdapter.name}

    for adapter in _DOCTYPES:
        assert adapter in declarable or adapter in routed or adapter in fallback, (
            f"{adapter!r} has a doctype but no route, no declared-adapter slot, and is "
            "not the fallback adapter"
        )


def test_the_llm_adapter_is_deliberately_not_in_routing() -> None:
    """Pins the boundary rather than leaving it to a comment: if the LLM adapter ever
    appears in ROUTING, the model has started deciding what documents ARE, which
    docs/INGESTION.md rules out ("never by sniffing message bodies")."""
    from app.ingest.llm_adapter import LlmDocumentAdapter

    routed = {adapter for adapter, _route in file_validation.ROUTING.values()}
    assert LlmDocumentAdapter.name not in routed


def test_every_document_kind_has_a_label() -> None:
    """A kind with no label reads as an empty phrase in the mismatch error, which is how
    "please upload a  instead" reaches a user."""
    kinds = {
        value
        for name, value in vars(file_validation).items()
        if name.startswith("DOC_") and isinstance(value, str)
    }
    assert kinds <= set(file_validation.LABELS), (
        f"missing from LABELS: {sorted(kinds - set(file_validation.LABELS))}"
    )


def test_routing_targets_a_real_upload_route() -> None:
    """The route string is shown to a person as "use /ingest/xlsx instead". A typo here
    sends them somewhere that does not exist."""
    from app.routers.ingest import router

    # router.routes carries the mounted prefix already, so ROUTING's "/ingest/xlsx"
    # compares directly -- no stripping.
    paths = {route.path for route in router.routes}
    for document, (_adapter, route) in sorted(file_validation.ROUTING.items()):
        assert route in paths, f"{document}: ROUTING names {route!r}, which is not a route"
