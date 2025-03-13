import os
import re
import sys
import threading
import tomllib
import socketserver
import socket
import json
import subprocess
import argparse
import base64
import zlib
import ipaddress
import pathlib


def qr_encode(obj: dict):
    from qrcode.main import QRCode
    json_str = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    compressed = zlib.compress(json_str.encode())
    base64_str = base64.b64encode(compressed).decode("ascii")
    qr = QRCode()
    qr.add_data(base64_str)
    qr.make()
    return qr


def get_wlan(host: str):
    if host != "0.0.0.0":
        return host
    for ip in socket.gethostbyname_ex(socket.gethostname())[-1]:
        if ipaddress.ip_address(ip).is_private:
            return ip
    return "127.0.0.1"


def create_servers(config, config_file):
    servers = []
    for pad, pad_config in config.items():
        if not isinstance(pad_config, dict):
            print(f"[Error] Invalid configuration for pad '{pad}'.")
            continue

        pad_config["name"] = pad
        pad_host = pad_config.setdefault("host", "0.0.0.0")
        pad_port = pad_config.setdefault("port", 8080)
        pad_type = pad_config.setdefault("type", "UDP").upper()
        pad_rules = pad_config.setdefault("rules", {})

        pad_config["fstring_sim"] = pad_config.get("fstring_sim", True)
        pad_config["format_map"] = pad_config.get("format_map", True)
        pad_config["default_eval"] = pad_config.get("default_eval", "sh").lower()
        pad_config["call_sync"] = pad_config.get("call_sync", "threaded_async").lower()

        if not isinstance(pad_port, int):
            print(f"[Error] Port in pad '{pad}' is not a integer.")
            continue

        if not isinstance(pad_rules, dict):
            print(f"[Error] Rules in pad '{pad}' are not in the correct format.")
            continue

        if not isinstance(pad_config["fstring_sim"], bool):
            print(f"[Error] 'fstring_sim' in pad '{pad}' is not a boolean true or false.")
            continue

        if not isinstance(pad_config["format_map"], bool):
            print(f"[Error] 'format_map' in pad '{pad}' is not a boolean true or false.")
            continue

        choices = ("sh", "bash", "cmd", "powershell",
                   "pwsh", "py", "eval", "exec")
        if pad_config["default_eval"] not in choices:
            print(f"[Error] 'default_eval' in pad '{pad}' should be one of {repr(choices)}")
            continue

        choices = ("simple", "threaded_sync", "threaded_async")
        if pad_config["call_sync"] not in choices:
            print(f"[Error] 'call_sync' in pad '{pad}' should be one of {repr(choices)}")
            continue

        server_address = (pad_host, pad_port)
        match pad_type:
            case "TCP":
                ServerClass = TCPServer
                RequestHandlerClass = TCPHandler
            case "UDP":
                ServerClass = UDPServer
                RequestHandlerClass = UDPHandler
            case _type:
                print(f"[Error] Server type '{_type}' in pad '{
                    pad}' is invalid, only 'TCP' and 'UDP' supported")
                continue

        # Start server thread
        server = ServerClass(server_address, RequestHandlerClass)
        server.setup_rules(pad_rules, pad_config)
        if pad_config.get("display_qr"):
            server.display_qr(pad_config, config_file)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.start()
        print(f"{pad_type} Server {
            server_address} running in thread {server_thread.name}")
        servers.append((server, server_thread))
    return servers


class RulesMixIn(socketserver.BaseServer):
    def setup_rules(self, pad_rules: dict[str, str], pad_config: dict):
        self.memo = {}  # memory-persistent data storage to manipulate complex operations
        self.rules: dict[str, list[tuple[str | None, str | list[str]]]] = {}
        self.default_eval: str = pad_config["default_eval"]
        self.call_sync: str = pad_config["call_sync"]
        self.fstring_sim: bool = pad_config["fstring_sim"]
        self.format_map: bool = pad_config["format_map"]

        for key, value in pad_rules.items():
            key_parts: list[str] = key.split("-")
            if len(key_parts) <= 1:
                print(f"[Error] rule '{
                      key}' is not well formed, need to have at least one '-' delimiter.")
                continue

            rule_id = key_parts[0] + '-' + key_parts[1].lower()
            eval_type = key_parts[2].lower() if len(key_parts) >= 3 else None
            rule_list = self.rules.setdefault(rule_id, [])

            if isinstance(value, str):
                rule_list.append((eval_type, value))

            elif isinstance(value, list):
                match ((eval_type or self.default_eval), value):
                    case (_, []):
                        print(f"[Error] Empty command list for rule '{key}'.")
                        continue

                    case ("exec", [cmd0, *_]) if isinstance(cmd0, str):
                        rule_list.append((eval_type, value))  # type: ignore

                    case ("exec", [cmd0, *_]) if isinstance(cmd0, list):
                        for cmd in value:
                            rule_list.append((eval_type, cmd))

                    case (_, [cmd0, *_]) if isinstance(cmd0, str):
                        for cmd in value:
                            rule_list.append((eval_type, cmd))

                    case _:
                        print(f"[Error] Unsupported value type in rule '{
                              key}': {type(value[0]).__name__}")
                        continue

            else:
                print(f"[Error] Unsupported value type for rule '{
                      key}': {type(value).__name__}")
                continue

    def display_qr(self, pad_config: dict, config_file: str):
        template_path = pathlib.Path(config_file)\
            .with_name(pad_config["name"]).with_suffix(".json")
        if template_path.is_file():
            with open(template_path, "rb") as f:
                template = json.load(f)
        else:
            template = {}

        pad_items, width, height = self._gen_pad_items(
            template.get("controlPadItems", []))

        qr_data = {
            "controlPad": template.get("controlPad") or {
                "name": pad_config["name"],
                "orientation": "PORTRAIT",
                "width": width,
                "height": height
            },
            "connectionConfig": {
                "controlPadId": 0,
                "connectionType": pad_config["type"],
                "configJson": json.dumps({
                    "host": get_wlan(pad_config["host"]),
                    "port": pad_config["port"]
                })
            },
            "controlPadItems": pad_items
        }

        qr = qr_encode(qr_data)
        qr.print_ascii(invert=True)
        qr.make_image().show()

    def _gen_pad_items(self, template_items: list[dict]):
        width = 1080
        height = 1920

        # math to make a litle grid of items, very good with lots of buttons
        def offsets(i: int):
            cols = 4
            rows = 8
            offset = width / 20
            offlmt = cols * rows
            return {
                "offsetX": ((i % cols) * width / cols) + (offset * (i // offlmt)),
                "offsetY": ((i // cols) % rows * height / rows) + (offset * (i // offlmt)),
            }

        elements: set[tuple[str, str]] = set()
        el_acts: dict[str, set[str]] = {}
        for rule in self.rules:
            ctl_id, action = rule.split("-")

            match action:
                case "switch" | "true" | "false":
                    ctl_type = "SWITCH"
                case "joy":
                    ctl_type = "JOYSTICK"
                case "slider":
                    ctl_type = "SLIDER"
                case "button" | "press" | "release" | "click":
                    ctl_type = "BUTTON"
                case _ if action.startswith("dp_"):
                    ctl_type = "DPAD"
                case _:
                    print(f"[WARNING] Invalid action '{action}'")
                    continue
            elements.add((ctl_id, ctl_type))
            el_acts.setdefault(ctl_id, set()).add(action)

        has_template = bool(template_items)
        template_items_bare = [
            (str(e["itemIdentifier"]), str(e["itemType"])) for e in template_items]
        pad_items = []
        for i, (ctl_id, ctl_type) in enumerate(sorted(elements)):

            try:
                index = template_items_bare.index((ctl_id, ctl_type))
                template_items_bare.pop(index)
                pad_item = template_items.pop(index)
            except ValueError:
                pad_item = {}

            pad_items.append(pad_item)

            pad_item.update({
                "controlPadId": 0,
                "itemIdentifier": ctl_id,
                "itemType": ctl_type,
            })
            if not has_template:
                pad_item.update(offsets(i))

            props: dict = json.loads(pad_item.get("properties", "{}"))
            acts = el_acts[ctl_id]

            if ctl_type == "BUTTON":
                # text is limited to 8 bytes currently
                if not props.get("text"):
                    props["text"] = ctl_id.title().replace("_", "")[:8]

                # prioritize press+release, otherwise click
                if None != props.get("useClickAction"):
                    pass
                elif {"press", "release"}.issubset(acts):
                    pass
                elif "click" in acts:
                    props["useClickAction"] = True
            elif ctl_type == "DPAD":
                if None != props.get("useClickAction"):
                    pass
                elif {"dp_press", "dp_release"}.issubset(acts):
                    pass
                elif acts.intersection({
                    "dp_click", "dp_left_click", "dp_right_click",
                        "dp_up_click", "dp_down_click"}):
                    props["useClickAction"] = True

            if props:
                pad_item["properties"] = json.dumps(props)

        # add missing template_items
        for pad_item, (ctl_id, ctl_type) in zip(template_items, template_items_bare):
            if (ctl_id, ctl_type) not in elements and ctl_type != "LABEL":
                continue
            pad_item.update({"controlPadId": 0})
            pad_items.append(pad_item)

        return pad_items, width, height

    def on_event(self, event: dict):
        rules_ids = self.event_ruleids(event)

        if not set(rules_ids).intersection(self.rules):
            print(f"[Warning] None of these rules were found: {rules_ids}")
            return

        for rule_id in rules_ids:
            if rule_id not in self.rules:
                continue

            # print(f"[Info] Running rule '{rule_id}':")
            for (eval_type, cmd) in self.rules[rule_id]:
                self.run_command(
                    event,
                    (
                        self.cmd_format(event, cmd) if isinstance(cmd, str) else
                        [self.cmd_format(event, c) for c in cmd]
                    ),
                    (eval_type or self.default_eval)
                )

    def run_command(self, event: dict, command: str | list[str], eval_type: str):
        target = subprocess.run
        args = tuple()

        match eval_type.lower():
            case "exec":
                args = (command if isinstance(command, list) else [command],)
            case _ if isinstance(command, list):
                assert False, f"[Error] Unsupported eval_type '{
                    eval_type}' using a list"
            case "sh":
                args = (["sh", "-c", command],)
            case "bash":
                args = (["bash", "-c", command],)
            case "cmd":
                args = (["cmd", "/C", command],)
            case "powershell":
                args = (["powershell", "-Command", command],)
            case "pwsh":
                args = (["pwsh", "-Command", command],)
            case "py":
                args = (["python", "-c", command],)
            case "eval":
                # simple match will add the values to the scope
                memo = self.memo
                match event:
                    case {"id": id, "type": "SWITCH" | "BUTTON" as type, "state": state}: pass
                    case {"id": id, "type": "DPAD" as type, "state": state, "button": button}: pass
                    case {"id": id, "type": "JOYSTICK" as type, "x": x, "y": y}: pass
                    case {"id": id, "type": "SLIDER" as type, "value": value}: pass
                    case _: pass

                target = eval
                args = (command, globals(), locals())
            case _:
                print(f"[Error] Unsupported eval type '{eval_type}'")
                return

        match self.call_sync:
            case "simple":
                target(*args)  # type: ignore
            case "threaded_async":
                threading.Thread(target=target, args=args).start()
            case "threaded_sync":
                thread = threading.Thread(target=target, args=args)
                thread.start()
                thread.join()
            case _:
                assert False, f"[Error] Unsupported call_sync '{self.call_sync}'"

    def event_ruleids(self, event: dict):
        match event:
            case {"id": id, "type": "SWITCH" | "BUTTON" as type, "state": state}:
                return (f"{id}-{type.lower()}",
                        f"{id}-{str(state).lower()}")

            case {"id": id, "type": "JOYSTICK"}:
                return (f"{id}-joy", )

            case {"id": id, "type": "SLIDER"}:
                return (f"{id}-slider", )

            case {"id": id, "type": "DPAD", "state": state, "button": btn}:
                return (f"{id}-dp_button",
                        f"{id}-dp_{state.lower()}",
                        f"{id}-dp_{btn.lower()}_{state.lower()}")

            case _:
                assert False, f"[Error] Event without any possible rules: {event}"

    def cmd_format(self, event: dict, command: str):
        # will find the pattern __{}__ and interpret as a fstring
        if self.fstring_sim:
            # simple match will add the values to the scope
            memo = self.memo
            match event:
                case {"id": id, "type": "SWITCH" | "BUTTON" as type, "state": state}: pass
                case {"id": id, "type": "DPAD" as type, "state": state, "button": button}: pass
                case {"id": id, "type": "JOYSTICK" as type, "x": x, "y": y}: pass
                case {"id": id, "type": "SLIDER" as type, "value": value}: pass
                case _: pass

            matches = re.split(r"__{(.+?)}__", command)
            for i in range(1, len(matches), 2):
                matches[i] = str(eval('f"{' + matches[i] + '}"'))
            command = "".join(matches)

        # any other {} will be passed to common format()
        if self.format_map:
            command = command.format_map(event)

        return command


class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.__getattribute__("on_event")(
            json.loads(self.request[0].strip()))


class TCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        # self.request is the TCP socket connected to the client
        data = b""

        while True:
            _data = self.request.recv(1024).strip()
            if not _data:
                break
            data += _data

            while -1 != (pos := data.find(b'}')):
                event, data = (data[:pos+1], data[pos+1:])
                self.server.__getattribute__("on_event")(json.loads(event))


class TCPServer(RulesMixIn, socketserver.ThreadingTCPServer):
    pass


class UDPServer(RulesMixIn, socketserver.UDPServer):
    pass  # A thread for each UDP datagram is overkill


def main():
    parser = argparse.ArgumentParser(
        description="Droidpad server configured with a TOML file \
            supporting multiple TCP/UDP servers together",
        allow_abbrev=False
    )
    parser.add_argument('config_file', nargs='?',
                        default=os.path.join(sys.path[0], "default.toml"))
    parser.add_argument("--qr", help="display QR Code on startup",
                        dest="display_qr", action=argparse.BooleanOptionalAction)

    args = parser.parse_args()

    with open(args.config_file, "rb") as f:
        config = tomllib.load(f)

    if None != args.display_qr:
        for pad_config in config.values():
            pad_config["display_qr"] = args.display_qr

    create_servers(config, args.config_file)


if __name__ == "__main__":
    main()
