"""
Coleta M1 (prefixos visíveis por ASN) e M6 (cobertura RPKI) via RIPEstat API.
BGP representa o plano de controle: os prefixos observados refletem anúncios BGP,
não necessariamente conectividade física.
"""

import requests
import pandas as pd
import time
import sys
import os

ASNS = [9988, 136168, 132748, 132167]
BASE = "https://stat.ripe.net/data"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(SCRIPT_DIR), "dados")


def get_announced_prefixes(asn):
    url = (f"{BASE}/announced-prefixes/data.json"
           f"?resource=AS{asn}&starttime=2021-01-01&endtime=2021-04-28")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()["data"]
    prefixes = data.get("prefixes", [])
    rows = []
    for p in prefixes:
        prefix = p["prefix"]
        for ts in p.get("timelines", []):
            starttime = ts.get("starttime", "")
            endtime = ts.get("endtime", "")
            rows.append({"asn": asn, "prefix": prefix,
                         "starttime": starttime, "endtime": endtime})
    return prefixes, rows


def get_rpki_validity(asn, prefix):
    url = (f"{BASE}/rpki-validation/data.json"
           f"?resource=AS{asn}&prefix={prefix}")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        status = r.json()["data"].get("status", "unknown")
        return status
    except Exception:
        return "error"


def collect_m1():
    print("=== M1: Prefixos visíveis por ASN ===")
    all_rows = []
    prefix_map = {}  # asn -> list of prefixes

    for asn in ASNS:
        print(f"  AS{asn}...", end=" ", flush=True)
        try:
            prefixes_raw, rows = get_announced_prefixes(asn)
            prefix_map[asn] = [p["prefix"] for p in prefixes_raw]
            count = len(prefix_map[asn])
            all_rows.append({"asn": asn, "num_prefixos": count})
            print(f"{count} prefixos")
        except Exception as e:
            print(f"ERRO: {e}")
            prefix_map[asn] = []
            all_rows.append({"asn": asn, "num_prefixos": 0})
        time.sleep(1)

    df = pd.DataFrame(all_rows)
    out_path = f"{OUT}/m1_prefixos_visiveis.csv"
    df.to_csv(out_path, index=False)
    print(f"  Salvo: {out_path}")
    return prefix_map


def collect_m6(prefix_map):
    print("\n=== M6: Cobertura RPKI ===")
    rows = []

    for asn, prefixes in prefix_map.items():
        print(f"  AS{asn}: verificando {len(prefixes)} prefixos...")
        valid = 0
        for prefix in prefixes[:50]:  # limitar a 50 para não sobrecarregar a API
            status = get_rpki_validity(asn, prefix)
            if status == "valid":
                valid += 1
            time.sleep(0.3)

        total = len(prefixes)
        cobertura = round(valid / total * 100, 1) if total > 0 else 0
        rows.append({"asn": asn, "total_prefixos": total,
                     "com_roa": valid, "cobertura_pct": cobertura})
        print(f"    {valid}/{total} com ROA válido ({cobertura}%)")

    df = pd.DataFrame(rows)
    out_path = f"{OUT}/m6_cobertura_rpki.csv"
    df.to_csv(out_path, index=False)
    print(f"  Salvo: {out_path}")


if __name__ == "__main__":
    prefix_map = collect_m1()
    collect_m6(prefix_map)
    print("\nConcluído.")
