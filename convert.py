import os

import requests
import yaml


def fetch_remote_txt(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def fetch_proxy_providers():
    pass

def main():
    with open("clash-template.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    remote_url = "https://raw.githubusercontent.com/devojony/collectSub/refs/heads/main/sub/sub_all_clash.txt"
    content = fetch_remote_txt(remote_url)
    proxy_providers = [p for p in content.split("\n") if p.strip()]

    config["proxy-providers"] = {
        f"provider#{i}": {
            "type": "http",
            "url": pp.strip(),
            "interval": 3600,
            "health-check": {
                "enable": True,
                "interval": 600,
                "url": "http://www.gstatic.com/generate_204",
            },
        }
        for i, pp in enumerate(proxy_providers)
    }

    os.makedirs("clash", exist_ok=True)
    with open(os.path.join("clash", "subs.yaml"), "w", encoding="utf-8") as file:
        yaml.dump(config, file, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    main()
