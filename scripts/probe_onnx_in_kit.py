"""Kit startup script (run with kit --exec): can a neural network run INSIDE the Kit process?

Installs onnx + onnxruntime-directml into Kit's Python with omni.kit.pipapi (the same way the
extension gets OpenCV), builds a small convolutional network with onnx.helper (no download of
weights), and times inference on a 640x480 RGB input with the DirectML (GPU) and CPU
providers. Used by scripts/probe_onnx_in_kit.ps1. Feasibility check only: the network is
random, its outputs mean nothing.
"""

import asyncio
import time
import traceback

import carb
import omni.kit.app
import omni.kit.pipapi

TAG = "[probe_onnx]"


def build_model():
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    nodes, inits, x = [], [], "input"
    channels = [3, 16, 32, 64, 128]
    for i in range(4):  # 4 x (3x3 conv stride 2 + ReLU), like a tiny backbone
        w = numpy_helper.from_array(rng.normal(0, 0.1, (channels[i + 1], channels[i], 3, 3)).astype(np.float32), f"w{i}")
        inits.append(w)
        nodes.append(helper.make_node("Conv", [x, f"w{i}"], [f"c{i}"], strides=[2, 2], pads=[1, 1, 1, 1]))
        nodes.append(helper.make_node("Relu", [f"c{i}"], [f"r{i}"]))
        x = f"r{i}"
    nodes.append(helper.make_node("GlobalAveragePool", [x], ["pooled"]))
    nodes.append(helper.make_node("Flatten", ["pooled"], ["feat"]))
    inits.append(numpy_helper.from_array(rng.normal(0, 0.1, (128, 2)).astype(np.float32), "fc"))
    nodes.append(helper.make_node("MatMul", ["feat", "fc"], ["logits"]))
    graph = helper.make_graph(nodes, "tiny_inspector",
                              [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 480, 640])],
                              [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 2])], inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    return model.SerializeToString()


async def _main():
    app = omni.kit.app.get_app()
    code = 1
    try:
        t0 = time.time()
        ok = omni.kit.pipapi.install("onnx", module="onnx") and \
            omni.kit.pipapi.install("onnxruntime-directml", module="onnxruntime")
        print(f"{TAG} pip install ok={ok} ({time.time() - t0:.1f}s)")
        import numpy as np
        import onnxruntime as ort

        print(f"{TAG} onnxruntime {ort.__version__}, available providers {ort.get_available_providers()}")
        model = build_model()
        x = np.random.default_rng(1).random((1, 3, 480, 640), dtype=np.float32)
        for providers in (["DmlExecutionProvider", "CPUExecutionProvider"], ["CPUExecutionProvider"]):
            if providers[0] not in ort.get_available_providers():
                print(f"{TAG} {providers[0]}: not available")
                continue
            sess = ort.InferenceSession(model, providers=providers)
            sess.run(None, {"input": x})  # warm-up
            times = []
            for _ in range(30):
                t = time.perf_counter()
                out = sess.run(None, {"input": x})[0]
                times.append((time.perf_counter() - t) * 1000)
                await app.next_update_async()  # interleaved with Kit updates, like the inspection loop
            times.sort()
            print(f"{TAG} {sess.get_providers()[0]}: output {out.shape}, "
                  f"median {times[len(times) // 2]:.2f} ms, p95 {times[int(len(times) * 0.95) - 1]:.2f} ms")
        code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
