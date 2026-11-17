
from decimal import Decimal, InvalidOperation


def converter_centavos(valor):
    valor = valor.strip()
    valor = valor.replace("R$", "").replace(" ", "")

    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")

    try:
        numero = Decimal(valor)

        if not numero.is_finite() or numero <= 0:
            raise ValueError("O valor deve ser maior que zero.")

        if numero != numero.quantize(Decimal("0.01")):
            raise ValueError("Utilize no máximo duas casas decimais.")

        return int(numero * 100)

    except InvalidOperation:
        raise ValueError("Digite um valor monetário válido.")


def formatar_reais(centavos):
    valor = f"{centavos / 100:,.2f}"

    valor = (
        valor.replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    return f"R$ {valor}"
