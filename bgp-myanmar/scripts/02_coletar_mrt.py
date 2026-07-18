"""
Coleta M2 (withdrawals), M3 (AS_PATH médio), M4 (concentração upstreams),
M5 (hijack 104.244.42.0/24) via MRT dumps do RouteViews.

Uso:
  python3 02_coletar_mrt.py --modo m5          # só hijack (5 fev 2021)
  python3 02_coletar_mrt.py --modo completo    # tudo (jan-abr 2021, ~2 GB)
  python3 02_coletar_mrt.py --modo withdrawals # só M2 (31 jan - 28 abr)
"""

import os
import sys
import gzip
import struct
import argparse
import requests
import mrtparse
import pandas as pd
from datetime import datetime, timedelta, timezone
from collections import defaultdict

ASNS_MYANMAR = {9988, 136168, 132748, 132167}
HIJACK_PREFIX = "104.244.42.0/24"
ROUTEVIEWS_BASE = "http://archive.routeviews.org/bgpdata"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(SCRIPT_DIR), "dados")
TMP = os.path.join(os.path.dirname(SCRIPT_DIR), "temp_mrt")

os.makedirs(TMP, exist_ok=True)
os.makedirs(OUT, exist_ok=True)


def list_update_files(year_month):
    """Lista arquivos de update disponíveis para um mês (ex: '2021.02')."""
    url = f"{ROUTEVIEWS_BASE}/{year_month}/UPDATES/"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    lines = r.text.splitlines()
    files = []
    for line in lines:
        if "updates." in line and ".bz2" in line:
            parts = line.split('"')
            for p in parts:
                if p.startswith("updates.") and p.endswith(".bz2"):
                    files.append(p)
    return files


def download_file(year_month, filename):
    url = f"{ROUTEVIEWS_BASE}/{year_month}/UPDATES/{filename}"
    dest = os.path.join(TMP, filename)
    if os.path.exists(dest):
        return dest
    print(f"    Baixando {filename}...", end=" ", flush=True)
    r = requests.get(url, timeout=120, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    size_kb = os.path.getsize(dest) // 1024
    print(f"{size_kb} KB")
    return dest


def get_dict_val(d):
    """Retorna o primeiro valor de um dict {key: value} como usado pelo mrtparse."""
    if isinstance(d, dict) and d:
        return list(d.values())[0]
    return d


def get_ts(entry):
    """Extrai timestamp Unix de entry (dict com chave numérica como string)."""
    ts_dict = entry.get("timestamp", {})
    if isinstance(ts_dict, dict) and ts_dict:
        return int(list(ts_dict.keys())[0])
    return int(ts_dict) if ts_dict else 0


def parse_as_path(path_attr):
    """Extrai lista de ASNs string de um atributo AS_PATH."""
    asns = []
    if not path_attr:
        return asns
    for seg in path_attr:
        asns.extend(seg.get("value", []))
    return [str(x) for x in asns]


def process_update_file(filepath, mode, withdrawals_acc, hijack_acc, aspath_acc, upstream_acc):
    """Processa um arquivo MRT de update."""
    try:
        reader = mrtparse.Reader(filepath)
    except Exception as e:
        print(f"    ERRO ao abrir {filepath}: {e}")
        return

    ASNS_STR = {str(a) for a in ASNS_MYANMAR}
    HIJACK_IP = HIJACK_PREFIX.split("/")[0]

    for rec in reader:
        try:
            entry = rec.data
            if not isinstance(entry, dict):
                continue

            ts = get_ts(entry)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)

            bgp_msg = entry.get("bgp_message", {})
            if not isinstance(bgp_msg, dict):
                continue

            msg_type_name = get_dict_val(bgp_msg.get("type", {}))
            if msg_type_name != "UPDATE":
                continue

            peer_asn = str(entry.get("peer_as", "0"))
            path_attrs = bgp_msg.get("path_attributes", [])

            # Extrair AS_PATH
            as_path_asns = []
            origin_as = None
            for attr in path_attrs:
                if not isinstance(attr, dict):
                    continue
                atype_name = get_dict_val(attr.get("type", {}))
                if atype_name == "AS_PATH":
                    as_path_asns = parse_as_path(attr.get("value", []))
                    if as_path_asns:
                        origin_as = as_path_asns[-1]

            # M2: Withdrawals
            withdrawn = bgp_msg.get("withdrawn_routes", [])
            if withdrawn and mode in ("completo", "withdrawals"):
                hour_key = dt.replace(minute=0, second=0, microsecond=0)
                asn_key = None
                if origin_as in ASNS_STR:
                    asn_key = int(origin_as)
                elif peer_asn in ASNS_STR:
                    asn_key = int(peer_asn)
                if asn_key:
                    withdrawals_acc[(hour_key, asn_key)] += len(withdrawn)

            # M5: Hijack do Twitter
            nlri = bgp_msg.get("nlri", [])
            for pfx_entry in nlri:
                if isinstance(pfx_entry, dict):
                    pfx_ip = pfx_entry.get("prefix", "")
                    pfx_len = pfx_entry.get("length", 24)
                    if HIJACK_IP in pfx_ip:
                        hijack_acc.append({
                            "timestamp": dt.isoformat(),
                            "prefix": f"{pfx_ip}/{pfx_len}",
                            "origin_as": origin_as,
                            "peer_asn": peer_asn,
                            "as_path": " ".join(as_path_asns),
                        })

            # M3: AS_PATH médio
            if as_path_asns and origin_as in ASNS_STR and mode == "completo":
                date_key = dt.date()
                aspath_acc[(date_key, int(origin_as))].append(len(as_path_asns))

            # M4: Upstreams
            if len(as_path_asns) >= 3 and origin_as in ASNS_STR and mode == "completo":
                for mid_as in as_path_asns[:-1]:
                    if mid_as not in ASNS_STR:
                        upstream_acc[int(origin_as)][mid_as] += 1

        except Exception:
            continue


def collect_m5():
    """M5: Hijack 5 fev 2021 — baixar apenas os updates desse dia."""
    print("=== M5: Hijack BGP do Twitter (5 fev 2021) ===")
    year_month = "2021.02"

    try:
        all_files = list_update_files(year_month)
    except Exception as e:
        print(f"  ERRO ao listar arquivos: {e}")
        # Usar nomes conhecidos baseados no padrão RouteViews
        all_files = [f"updates.20210205.{h:02d}{m:02d}.bz2"
                     for h in range(24) for m in (0, 15, 30, 45)]

    # Filtrar apenas 5 fev
    day_files = [f for f in all_files if "20210205" in f]
    print(f"  {len(day_files)} arquivos de update para 5 fev 2021")

    hijack_acc = []
    withdrawals_acc = defaultdict(int)
    aspath_acc = defaultdict(list)
    upstream_acc = defaultdict(lambda: defaultdict(int))

    for fname in sorted(day_files):
        try:
            fpath = download_file(year_month, fname)
            process_update_file(fpath, "m5", withdrawals_acc, hijack_acc, aspath_acc, upstream_acc)
        except Exception as e:
            print(f"    ERRO em {fname}: {e}")

    df = pd.DataFrame(hijack_acc)
    out_path = f"{OUT}/m5_hijack_104_244_42_0.csv"
    df.to_csv(out_path, index=False)
    print(f"  {len(df)} anúncios do prefixo registrados.")
    print(f"  Salvo: {out_path}")
    return df


def collect_withdrawals():
    """M2: Withdrawals por hora, 31 jan – 28 abr 2021."""
    print("=== M2: Withdrawals por hora ===")
    months = ["2021.01", "2021.02", "2021.03", "2021.04"]
    withdrawals_acc = defaultdict(int)
    hijack_acc = []
    aspath_acc = defaultdict(list)
    upstream_acc = defaultdict(lambda: defaultdict(int))

    for ym in months:
        print(f"  Mês {ym}...")
        try:
            all_files = list_update_files(ym)
        except Exception as e:
            print(f"    ERRO: {e}")
            continue

        # Para jan, só a partir do dia 31
        if ym == "2021.01":
            all_files = [f for f in all_files if "20210131" in f or "20210130" in f]
        # Para abr, só até dia 28
        elif ym == "2021.04":
            all_files = [f for f in all_files
                         if any(f"202104{d:02d}" in f for d in range(1, 29))]

        for fname in sorted(all_files):
            try:
                fpath = download_file(ym, fname)
                process_update_file(fpath, "withdrawals", withdrawals_acc,
                                    hijack_acc, aspath_acc, upstream_acc)
            except Exception as e:
                print(f"    ERRO em {fname}: {e}")

    rows = [{"timestamp_hora": k[0].isoformat(), "asn": k[1], "num_withdrawals": v}
            for k, v in withdrawals_acc.items()]
    df = pd.DataFrame(rows).sort_values("timestamp_hora")
    out_path = f"{OUT}/m2_withdrawals_por_hora.csv"
    df.to_csv(out_path, index=False)
    print(f"  Salvo: {out_path} ({len(df)} linhas)")


def collect_completo():
    """M2, M3, M4: Todos os dados, jan–abr 2021."""
    print("=== Coleta completa (M2, M3, M4) ===")
    months = ["2021.01", "2021.02", "2021.03", "2021.04"]
    withdrawals_acc = defaultdict(int)
    hijack_acc = []
    aspath_acc = defaultdict(list)
    upstream_acc = defaultdict(lambda: defaultdict(int))

    for ym in months:
        print(f"\n  Mês {ym}...")
        try:
            all_files = list_update_files(ym)
        except Exception as e:
            print(f"    ERRO: {e}")
            continue
        for fname in sorted(all_files):
            try:
                fpath = download_file(ym, fname)
                process_update_file(fpath, "completo", withdrawals_acc,
                                    hijack_acc, aspath_acc, upstream_acc)
            except Exception as e:
                print(f"    ERRO em {fname}: {e}")

    # M2
    rows2 = [{"timestamp_hora": k[0].isoformat(), "asn": k[1], "num_withdrawals": v}
              for k, v in withdrawals_acc.items()]
    pd.DataFrame(rows2).sort_values("timestamp_hora").to_csv(
        f"{OUT}/m2_withdrawals_por_hora.csv", index=False)

    # M3
    rows3 = [{"data": str(k[0]), "asn": k[1],
               "as_path_medio": round(sum(v) / len(v), 2)}
              for k, v in aspath_acc.items()]
    pd.DataFrame(rows3).sort_values("data").to_csv(
        f"{OUT}/m3_aspath_medio.csv", index=False)

    # M4
    rows4 = []
    for asn, ups in upstream_acc.items():
        total = sum(ups.values())
        for up_asn, freq in sorted(ups.items(), key=lambda x: -x[1])[:20]:
            rows4.append({"asn_monitorado": asn, "asn_upstream": up_asn,
                          "frequencia": freq,
                          "fracao_caminhos": round(freq / total, 4) if total else 0})
    pd.DataFrame(rows4).to_csv(f"{OUT}/m4_concentracao_upstreams.csv", index=False)

    print("\nConcluído.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--modo", choices=["m5", "withdrawals", "completo"],
                        default="m5")
    args = parser.parse_args()

    if args.modo == "m5":
        collect_m5()
    elif args.modo == "withdrawals":
        collect_withdrawals()
    else:
        collect_completo()
