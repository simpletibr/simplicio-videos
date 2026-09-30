# Venda ativa em massa — `simplicio-video prospect`

## Planilha de controle de vendas (única, no Drive)

Uma só planilha controla prospects, envios, respostas, preços e pagamentos. **Nunca criar outra nem cópia.**

- Arquivo: `controle-vendas-videos.xlsx` (Excel .xlsx de verdade, não convertido para Google Sheets)
- Pasta: `simplicio-video` (id `17OFuLyTCFyh9jG4Lb_GNnSpx-hcnHBfb`), conta wesleybob4
- **File id: `18uRagw8rS-FbEk_KM8E8h3r-5ytNO0hA`**
- Link: https://drive.google.com/file/d/18uRagw8rS-FbEk_KM8E8h3r-5ytNO0hA/view?usp=drivesdk
- Criada em 30/09/2026 18:30 (BRT) com `openpyxl` (script `/workspace/controle/build_controle.py` no box).
- Abas: `Prospects` (25 colunas; listas de status/canal/responsável/preço), `Resumo diario`, `Precos`, `Regras`,
  `Clientes` (WJR Informática Games e Lothus Odontologia, que não entram em Prospects).
- Carga inicial: as 10 empresas do piloto Dia das Crianças (`prospects-piloto/dia-criancas/lote.csv`), status
  `previa_pronta`, com fonte de cada dado em `fonte_dados`. `link_previa_drive` fica vazio até a prévia subir para o Drive.

Preços (aba `Precos`): R$ 120 cheio; R$ 80 oferta Dia das Crianças **só se o cliente perguntar**; R$ 60 três dias depois
se não fechar (`data_followup_60`). Nada vai para cliente sem o Wesley aprovar o lote (`aprovado_wesley` antes de
`enviado`). Sem falsa escassez. Atualizar todo dia.

### Como editar SEMPRE o mesmo arquivo (mesmo file id)

1. Antes de mexer, confirmar que só existe uma: `search_files` com
   `parentId = '17OFuLyTCFyh9jG4Lb_GNnSpx-hcnHBfb' and title contains 'controle'` → deve voltar só o id acima.
2. Baixar a versão atual: `DownloadFile` (conexão `user-Google-drive`, `fileId` acima) ou
   `download_file_content`. Editar localmente (openpyxl ou Excel) mantendo nome, abas e colunas.
3. Enviar o conteúdo como **nova versão do MESMO arquivo**: no Drive web (conta wesleybob4), botão direito no arquivo →
   **Gerenciar versões → Enviar nova versão** → escolher o .xlsx editado. O id e o link não mudam.
   (Equivalente por API: `PATCH https://www.googleapis.com/upload/drive/v3/files/18uRagw8rS-FbEk_KM8E8h3r-5ytNO0hA?uploadType=media`.)
4. Conferir com `get_file_metadata` (id acima): mesmo `id`, `modifiedTime` novo, `mimeType` ainda
   `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

Limites das ferramentas do agente (verificado em 30/09/2026):

- `update_file` do conector `user-Google-drive` **só altera nome e pasta** (metadados), **não o conteúdo**. Teste feito:
  `update_file` com o mesmo título → `id` igual, `modifiedTime` 21:30:06Z → 21:30:21Z (18:30 BRT), conteúdo intacto
  (download idêntico byte a byte ao enviado).
- `UploadFile`/`create_file` **sempre criam um arquivo novo** (id novo). **Não usar** para atualizar a planilha: isso gera
  duplicata. Se acontecer por engano, mandar o arquivo novo para a lixeira (`trash_file`) e refazer a edição no id acima.
- Sem ferramenta de upload de conteúdo para um id existente, o agente prepara o .xlsx editado no box e o Wesley (ou um
  agente com o navegador logado no Drive) faz o passo 3.
