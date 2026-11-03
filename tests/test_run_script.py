import run


def test_commands_are_built_for_each_platform():
    assert run.venv_python("nt").parts[-2:] == ("Scripts", "python.exe")
    assert run.venv_python("posix").parts[-2:] == ("bin", "python")


def test_env_file_is_created_once(tmp_path):
    (tmp_path / "env.example").write_text("KEY=\n", encoding="utf-8")
    run.prepare_env(tmp_path)
    (tmp_path / ".env").write_text("KEY=mine\n", encoding="utf-8")
    run.prepare_env(tmp_path)
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "KEY=mine\n"
