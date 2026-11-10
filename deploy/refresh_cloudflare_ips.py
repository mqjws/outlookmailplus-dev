import ipaddress
import urllib.request
from pathlib import Path


def main():
    networks = []
    for family in ("v4", "v6"):
        request = urllib.request.Request(
            f"https://www.cloudflare.com/ips-{family}",
            headers={"User-Agent": "OutlookEmailPlus-Deployment/2.7.0"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            entries = response.read().decode("ascii").splitlines()
        family_networks = [ipaddress.ip_network(entry.strip()) for entry in entries if entry.strip()]
        expected_version = 4 if family == "v4" else 6
        if not family_networks or any(network.version != expected_version for network in family_networks):
            raise RuntimeError("Invalid Cloudflare address list")
        networks.extend(family_networks)
    destination = Path(__file__).resolve().parent / "cloudflare-realip.conf"
    contents = "".join(f"set_real_ip_from {network};\n" for network in networks)
    contents += "real_ip_header CF-Connecting-IP;\nreal_ip_recursive on;\n"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(contents, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    print(f"Updated {destination.name}: {len(networks)} trusted networks")


if __name__ == "__main__":
    main()
