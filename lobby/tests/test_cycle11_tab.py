"""Recovery-code exports retain the displayed account without Tk or file writes."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open


class Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def controller():
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "show_codes"]
    file_open = mock_open()
    dialog = Mock(return_value="codes.txt")
    namespace = {"t": lambda text, **kwargs: text.format(**kwargs), "open": file_open,
                 "filedialog": SimpleNamespace(asksaveasfilename=dialog)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.client = SimpleNamespace(me={"name": "Original"})
    tab.server_var = Variable("Server-A")
    tab.view = SimpleNamespace(codes_window=Mock())
    tab.show_codes(["AAAA-BBBB-CCCC"])
    save = tab.view.codes_window.call_args.args[2]
    return tab, save, file_open, dialog


class RecoveryCodeExportOwnershipTest(unittest.TestCase):
    def assert_original_export(self, file_open):
        file_open.assert_called_once_with("codes.txt", "w", encoding="utf-8")
        file_open().write.assert_called_once_with(
            "T5DR Online recovery codes for Original on Server-A\nAAAA-BBBB-CCCC\n")

    def test_account_switch_before_save_keeps_original_codes_identity(self):
        tab, save, file_open, _dialog = controller()
        tab.client = SimpleNamespace(me={"name": "Replacement"})
        tab.server_var.set("Server-B")
        save(object())
        self.assert_original_export(file_open)

    def test_account_switch_during_file_dialog_keeps_original_codes_identity(self):
        tab, save, file_open, dialog = controller()

        def pick_file(**_kwargs):
            tab.client = SimpleNamespace(me={"name": "Replacement"})
            tab.server_var.set("Server-B")
            return "codes.txt"

        dialog.side_effect = pick_file
        save(object())
        self.assert_original_export(file_open)

    def test_disconnect_before_save_keeps_original_codes_identity(self):
        tab, save, file_open, _dialog = controller()
        tab.client = None
        tab.server_var.set("Server-B")
        save(object())
        self.assert_original_export(file_open)

    def test_cancelled_file_dialog_does_not_write(self):
        _tab, save, file_open, dialog = controller()
        dialog.return_value = ""
        save(object())
        file_open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
