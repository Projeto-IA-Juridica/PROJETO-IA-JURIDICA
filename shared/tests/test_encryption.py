from shared.security.encryption import (
    criptografar,
    descriptografar,
    hash_senha,
    mascarar_cpf,
    mascarar_telefone,
    verificar_senha,
)


def test_criptografia_reversivel_sucesso():
    texto_original = "12345678909"
    texto_cifrado = criptografar(texto_original)

    assert texto_cifrado != texto_original
    assert isinstance(texto_cifrado, str)

    texto_decifrado = descriptografar(texto_cifrado)
    assert texto_decifrado == texto_original


def test_criptografia_nulos_e_vazios():
    assert criptografar("") == ""
    assert criptografar(None) is None

    assert descriptografar("") == ""
    assert descriptografar(None) is None


def test_hash_senha_sucesso():
    senha_plana = "SenhaForte123!"
    hash_gerado = hash_senha(senha_plana)

    assert hash_gerado != senha_plana
    assert hash_gerado.startswith("$2b$") or hash_gerado.startswith("$2a$")  # Formato Bcrypt


def test_hash_senha_salts_diferentes():
    # O hash da mesma senha deve ser diferente devido ao salt aleatório
    senha_plana = "SenhaForte123!"
    hash1 = hash_senha(senha_plana)
    hash2 = hash_senha(senha_plana)

    assert hash1 != hash2


def test_verificacao_senha_correta():
    senha_plana = "MinhaSenha@2024"
    hash_salvo = hash_senha(senha_plana)

    # Verifica se a verificação passa para a senha correta
    resultado = verificar_senha(senha_plana, hash_salvo)
    assert resultado is True


def test_verificacao_senha_incorreta():
    senha_plana = "MinhaSenha@2024"
    senha_errada = "SenhaIncorreta"
    hash_salvo = hash_senha(senha_plana)

    # Verifica se a verificação falha para senha incorreta
    resultado = verificar_senha(senha_errada, hash_salvo)
    assert resultado is False


def test_mascaramento_cpf():
    # Testa mascaramento de CPF válido
    assert mascarar_cpf("12345678901") == "***.***.***-01"

    # Testa mascaramento de CPF já formatado e menor que 11 caracteres reais
    assert mascarar_cpf("123.456.789-10") == "***.***.***-10"


def test_mascaramento_cpf_invalido_curto():
    assert mascarar_cpf("12345") == "***.***.***-XX"


def test_mascaramento_cpf_vazio():
    assert mascarar_cpf("") == ""
    assert mascarar_cpf(None) is None


def test_mascaramento_telefone():
    # Testa formato comum de celular com DDI e DDD
    assert mascarar_telefone("5511999999999") == "(**) *****-9999"

    # Testa formato com pontuação
    assert mascarar_telefone("+55 (11) 98888-7777") == "(**) *****-7777"


def test_mascaramento_telefone_curto():
    assert mascarar_telefone("123") == "(**) *****-XXXX"


def test_mascaramento_telefone_vazio():
    assert mascarar_telefone("") == ""
    assert mascarar_telefone(None) is None
