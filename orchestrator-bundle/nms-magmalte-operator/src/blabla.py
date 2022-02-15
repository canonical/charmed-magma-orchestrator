from dataclasses import dataclass


@dataclass
class Port:
    """Class for keeping track of an item in inventory."""
    name: str
    port: int
    target_port: int = None
    node_port: int = None
    protocol: str = "TCP"

port = Port(name="whatever", port=1234, target_port=5679, node_port=9012, protocol="UDP")
