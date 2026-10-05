from backend.app.security import normalize_cpf, validate_cpf


def test_valid_cpf():
    assert validate_cpf("529.982.247-25")
    assert normalize_cpf("529.982.247-25") == "52998224725"


def test_invalid_cpf():
    assert not validate_cpf("111.111.111-11")
    assert not validate_cpf("123.456.789-00")
