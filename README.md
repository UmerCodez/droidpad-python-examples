## This Repository contains Python examples for [DroidPad](https://github.com/UmerCodez/DroidPad) Android app

1. ### Clone this Repo
```bash
git clone https://github.com/UmerCodez/droidpad-python-examples
```
2. ### Install requirements
```bash
pip install -r requirements.txt
```

3. ### Move to servers directory
```bash
cd droidpad-python-examples/servers
```
-  #### To Start a websocket server
    ```bash
     python websocket-server.py 8080
    ```
-  #### To Start a TCP server
    ```bash
     python tcp-server.py 8081
    ```
-  #### To Start a UDP server
    ```bash
     python udp-server.py 8082
    ```
### To find your machines's IP address:
  - On Windows, use the `ipconfig` command.
  - On Linux, use the `ifconfig` command.


Create a new controller in [DroidPad](https://github.com/UmerCodez/DroidPad). Then, navigate to the connection settings and specify the IP address and port number. Once connected, and you should see JSON messages being printed in the console.

---

### Bluetooth Low Energy (BLE) in DroidPad

DroidPad functions as a **BLE peripheral** and sends notifications containing `CSV` strings to connected client through the characteristic UUID: `dc3f5274-33ba-48de-8246-43bf8985b323`.

#### Steps to Connect:
1. **Start the GATT Server on DroidPad**:
   - Open a control pad with BLE connection and tap the **Play** button to initialize the GATT server and start advertising.

2. **Subscribe Using the Python Client**:
   - Navigate to the `BLEClient` directory in the DroidPad Python examples repository.
   - Run the `subscribe.py` script:

     ```bash
     python subscribe.py
     ```
   - This script performs the following:
     - Scans for nearby BLE devices advertising the service UUID: `4fbfc1d7-f509-44ab-afe1-62ea40a4b111`.
     - Subscribes to notifications from the characteristic UUID: `dc3f5274-33ba-48de-8246-43bf8985b323`.

3. **View Notifications**:
   - Once the script connects to DroidPad, it displays `CSV` strings in the console.
   - These notifications are triggered by interactions with items on the control pad.


---

### Configurable Server (by [imsamuka](https://github.com/imsamuka))

This server is configured with a [TOML](https://toml.io) file, and supports multiple TCP/UDP droidpad servers simultaneosly. Theres's a documented [default config file](configServer/default.toml) to use as a reference. There are other examples in the [configServer folder](configServer/).

### Usage


```bash
# Enter configServer directory
cd configServer
```

## Running Servers

```bash
python config-server.py [--qr] [CONFIG_FILE]

# Examples:

python config-server.py default.toml

python config-server.py linux/mouse-x11.toml
```

### Generating QR Code

You can use the `--qr` flag to display a QRCode to import the pads in the app.
This auto generated import is intended for development use only. The server will
also try to load a file `pad_name.json` adjacent to the `CONFIG_FILE` and use that
as a template to generate the QR Code, preserving element positions, scaling, colors,
and most other properties.


## Writing Server Configuration

The configuration is always composed of a `[pad_name]` and `[pad_name.rules]`. You can have more than one *pad* per file, but each one has to have these 2 sections.

## Pad configuration
In `[pad_name]` you declare the global configuration for this particular *pad*:

```toml
[example]

host = "0.0.0.0"
port = 8080
type = "UDP"
default_eval = "sh"
call_sync = "threaded_async"
fstring_sim = true
format_map = true
```

**The meaning of each field is explained in the [default configuration file](configServer/default.toml).** It's recommended for Windows users to change `default_eval` to `py`, `cmd` or `powershell`.

### Rules configuration

In `[pad_name.rules]` you declare all rules about the pad elements themselves.

```toml
[example.rules]

ctl_id-dp_press = "echo {id} {button} pressed"
ctl_id-dp_release = "echo {id} {button} released"
ctl_id-dp_click = "echo {id} {button} clicked"
```

Each rule field is composed of three parts separated by a `-` character, and a command or list of commands:

```toml
ELEMENTID-RULETYPE-EVALTYPE = "COMMAND"

ELEMENTID-RULETYPE-EVALTYPE = ["COMMAND_1", "COMMAND_2"]

ELEMENTID-RULETYPE-EVALTYPE = """
    MULTILINE_COMMAND
"""
```

- `ELEMENTID`: Is the ID you configure in the DroidPad App for a control element.
- `RULETYPE`: Determines the *type* of element and *when* the rule will activate. The possible choices for this part can be found in the [default configuration file](configServer/default.toml).
- `EVALTYPE`: Determines which program will be used to execute `COMMAND`. For example:

  - `-bash` will run `bash -c "COMMAND"`
  - `-py` will run `python -c "COMMAND"`

  If `-EVALTYPE` is missing, then the eval type declared in the `default_eval` configuration field is used instead.

- `COMMAND`: How it will be interpreted depends on the eval type.
  - If `format_map = true`, substrings like `{id} {type} {state} {button}` will be substituited by their values in the event received. For example, if a dpad left button was pressed, `{button}` will be substituited by `LEFT` and `{state}` by `PRESS`. Normal python formatting works, for example in a slider with value `0.9`, `{value:%}` will be `90%`.
  - If `fstring_sim = true`, substrings inside `__{ }__` will be interpreted like a python [f-string](https://docs.python.org/3/reference/lexical_analysis.html#f-strings). This means you can run python code BEFORE the actual command runs. All event fields are in scope, and a dictionary `memo` may be used to store other variables.
  - In the case of eval type `exec`, it expects a list of arguments instead of a single string, for example `["echo", "Element {id} sent a event"]`. If you want multiple commands, you need to use a list inside a list.

### Examples:

```toml

# After tapping a button with id 'turnoff'
# run the command: sh -c shutdown
turnoff-click-sh = "shutdown"

# After pressing/release button with id `mousebtn1`
# run the program 'xdotool' with default_eval
# to press/release the mouse left button
mousebtn1-press = "xdotool mousedown 1"
mousebtn1-release = "xdotool mouseup 1"

# The same as above, using __{}__ substitution
# uses `fstring_sim = true`
mousebtn1-button = "xdotool mouse__{'down' if state == 'PRESS' else 'up'}__ 1"

# When a joystick with id 'radius' sends a event
# Run a python script to print the calculated radius in degrees
radius-joy-py = """
import math

x = {x} # <-- uses `format_map = true` here
y = {y}
print('Radius: ', math.atan2(y, x) * 180.0 / math.pi)
"""

# Change the volume of the current media using a slider with id 'volume'
# Echo the current volume as a percentage
# uses `format_map = true`
volume-slider-sh = 'playerctl volume {value}; echo "Volume at {value:%}"'


# Convert every button press on a dpad with id 'arrows' to keyboard arrows
# __{button.title()}__ converts "RIGHT" to "Right"
arrows-dp_button = "xdotool key__{'down' if state == 'PRESS' else 'up'}__ __{button.title()}__"
```
