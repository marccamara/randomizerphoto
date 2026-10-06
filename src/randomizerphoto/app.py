def _run(n, model):
    STATE.update(done=0, total=0, running=True, finished=False, error=None)
    try:
        base = Path(STATE["base"])
        out = base / "photos_traitees"
        out.mkdir(exist_ok=True)
        process_folder_advanced(str(base), str(out), n, str(HIST), _progress, model)
    except Exception as e:
        STATE["error"] = str(e)
    finally:
        STATE.update(running=False, finished=True)
