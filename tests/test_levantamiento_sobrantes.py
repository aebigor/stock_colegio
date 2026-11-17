from app.modules.activos.levantamiento_service import calcular_diferencias_cantidad


def test_ten_delivered_twenty_found_means_ten_new():
    assert calcular_diferencias_cantidad(10, 20) == (10, 10, 0)


def test_ten_delivered_eight_found_means_two_missing():
    assert calcular_diferencias_cantidad(10, 8) == (8, 0, 2)


def test_ten_delivered_ten_found_means_no_difference():
    assert calcular_diferencias_cantidad(10, 10) == (10, 0, 0)


def test_counts_are_never_negative():
    assert calcular_diferencias_cantidad(10, -3) == (0, 0, 10)
