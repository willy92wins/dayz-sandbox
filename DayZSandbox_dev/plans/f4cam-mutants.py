"""F4 parte 1 §6: mutaciones F1-F12 del lado Python. Cada una se aplica, corre solo su prueba y se restaura.

Uso, desde DayZSandbox_dev/:  python3 plans/f4cam-mutants.py [F1,F5,...]
Sale 0 si mueren todas las elegidas. No corras otra suite a la vez.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BR = "app/backend/bridge.py"
CL = "app/backend/camera_live.py"
SV = "app/backend/server.py"
T = "app.tests.test_f4_camera."

ROLE = '            if order.get("role", "server") != "server":\n                continue\n'
MUTANTS = [
    ("F1", BR, "        for order in list(self.orders.values()):\n" + ROLE + "            if order[\"conn\"] == new_conn:",
     "        for order in list(self.orders.values()):\n            if order[\"conn\"] == new_conn:",
     T + "K13Servidor.test_k13_hello_del_servidor_no_toca_la_orden_del_cliente"),
    ("F2", BR, "            for order in list(self.orders.values()):\n                if order.get(\"role\", \"server\") != \"server\":\n                    continue\n                if order[\"conn\"] != old_conn:",
     "            for order in list(self.orders.values()):\n                if order[\"conn\"] != old_conn:",
     T + "K13Servidor.test_k13_perder_el_servidor_no_toca_la_orden_del_cliente"),
    ("F3", BR, "            if o.get(\"role\", \"server\") != peer:\n                continue\n            if o[\"bstate\"] != \"pendiente\":",
     "            if o[\"bstate\"] != \"pendiente\":", T + "K1Play.test_k1_play_args_exactos_rol_cliente_y_pose_inicial"),
    ("F4", BR, "                    order[\"bstate\"] = \"descartada\"\n                    if cl is not None:\n                        cl.on_dropped_locked(order, \"conexion_perdida\")",
     "                    pass", T + "K11HelloCliente"),
    ("F5", BR, "                if order.get(\"role\") == \"client\":\n                    order[\"bstate\"] = \"descartada\"",
     "                if False:\n                    order[\"bstate\"] = \"descartada\"", T + "K12Ttl"),
    ("F6", CL, "    if playing == 1 and active != 1:\n        return False\n", "", T + "V1LecturaValida"),
    ("F7", CL, "        return self._in_flight_order_locked() is not None", "        return False", T + "K8EnVuelo"),
    ("F8", CL, "\"c_yaw_mdeg\": [yaw_to_mdeg(key[\"yaw\"]) for key in keys]",
     "\"c_yaw_mdeg\": [round(float(key[\"yaw\"]) * 1000) for key in keys]", T + "K1Play.test_k1_play_args_exactos_rol_cliente_y_pose_inicial"),
    ("F9", SV, "                self.send_json(403, fail(\"forbidden\", \"Solo la persona rueda la camara\"))\n                return\n",
     "                pass\n", T + "K4Credenciales"),
    ("F10", CL, "or float(val) > wsize:", "or float(val) > wsize + 10:", T + "K7Limites"),
    ("F11", CL, "        self._last = {\n            \"op_id\": order[\"op_id\"], \"verb\": order[\"verb\"],\n            \"status\": status, \"reason\": reason,\n        }",
     "        self._cam = read.get(\"cam\")\n        self._last = {\n            \"op_id\": order[\"op_id\"], \"verb\": order[\"verb\"],\n            \"status\": status, \"reason\": reason,\n        }", T + "K9MuchoCamino"),
    ("F12", BR, "                if status == \"done\" and not valid_cam_read(read):", "                if False:", T + "K14LecturaRota"),
]


def main():
    pick = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    alive = []
    for mid, rel, old, new, test in MUTANTS:
        if pick and mid not in pick:
            continue
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if text.count(old) != 1:
            raise SystemExit("%s: el ancla aparece %d veces en %s" % (mid, text.count(old), rel))
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.replace(old, new))
            rc = subprocess.run([sys.executable, "-m", "unittest", test], cwd=ROOT,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        finally:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        verdict = "MUERE" if rc != 0 else "VIVE"
        if rc == 0:
            alive.append(mid)
        print(mid, verdict, flush=True)
    print("vivas: %s" % (",".join(alive) or "ninguna"))
    return 1 if alive else 0


if __name__ == "__main__":
    sys.exit(main())
