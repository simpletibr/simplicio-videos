# Licença

O simplicio-video é distribuído sob a **GNU Affero General Public License, versão 3 ou posterior (AGPL-3.0-or-later)**. O texto integral está em [LICENSE](../../LICENSE) e o aviso do produto em [NOTICE](../../NOTICE). A declaração no `pyproject.toml` é a expressão SPDX `license = "AGPL-3.0-or-later"`, com `license-files = ["LICENSE", "NOTICE"]` (a forma antiga, a tabela `{ text = ... }`, está depreciada e deixa de ser aceita pelo setuptools em 2027).

## Por que

- **Open source, sem venda.** O projeto é aberto e não é vendido como produto fechado. A AGPL é uma licença de software livre reconhecida pela OSI.
- **Proteção contra fork fechado como serviço.** A AGPL exige que quem modificar o código e oferecer o programa pela rede disponibilize as modificações sob a mesma licença. Isso impede que alguém rode uma versão fechada como serviço sem devolver as melhorias.
- **Compatível com as dependências.** As dependências permissivas (MIT, Apache-2.0, BSD e PSF) podem ser incorporadas num projeto AGPL. A allowlist do gate (`docs/host/licenses.md`) segue essa linha.
- **FSL descartada.** A Functional Source License foi avaliada e descartada porque não é open source: ela restringe o uso concorrente por dois anos antes de virar Apache-2.0. Um projeto que quer ser open source precisa de uma licença que a OSI reconheça.

Não é aconselhamento jurídico; revisão por advogado antes da publicação é recomendada.

## Contribuição

Contribuições entram sob a mesma licença do projeto (AGPL-3.0-or-later). Ao enviar um patch ou um pull request, quem contribui declara que tem o direito de licenciar o código dessa forma. Código de terceiros só entra se a licença dele for compatível com a allowlist e com a AGPL, e a origem precisa ficar registrada no próprio commit ou no doc da trilha.
