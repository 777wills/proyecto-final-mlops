"""El modelo responde correctamente ante una entrada definida."""

import numpy as np


def test_modelo_responde_con_entrada_definida(onnx_session, n_features):
    """El modelo debe devolver una salida valida para una entrada con el shape esperado."""
    input_name = onnx_session.get_inputs()[0].name
    output_names = [o.name for o in onnx_session.get_outputs()]

    # Entrada definida: un vector de ceros con el numero de features esperado.
    x = np.zeros((1, n_features), dtype=np.float32)
    outputs = onnx_session.run(output_names, {input_name: x})

    # Debe existir al menos una salida (la etiqueta).
    assert len(outputs) >= 1, "El modelo no devolvio ninguna salida"

    labels = np.asarray(outputs[0]).ravel()
    assert labels.shape[0] == 1, "Se esperaba exactamente una prediccion para una muestra"

    # La etiqueta debe ser una de las clases conocidas del problema binario.
    label = int(labels[0])
    assert label in (0, 1), f"Etiqueta fuera de rango: {label}"


def test_prediccion_es_determinista(onnx_session, n_features):
    """La misma entrada debe producir siempre la misma salida (modelo deterministico)."""
    input_name = onnx_session.get_inputs()[0].name
    output_names = [o.name for o in onnx_session.get_outputs()]

    x = np.ones((1, n_features), dtype=np.float32)
    out1 = onnx_session.run(output_names, {input_name: x})[0]
    out2 = onnx_session.run(output_names, {input_name: x})[0]

    np.testing.assert_array_equal(np.asarray(out1).ravel(), np.asarray(out2).ravel())
