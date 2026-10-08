<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quadro da fábrica</title>
<style>
:root {
  color-scheme: light;
  --fundo: #f4f5f7;
  --superficie: #ffffff;
  --texto: #1b1f24;
  --texto-suave: #4b5563;
  --borda: #cfd5dd;
  --link: #0a4f9c;
  --foco: #0a4f9c;
  --alerta: #9b1c1c;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --fundo: #111418;
    --superficie: #1b2027;
    --texto: #eef1f5;
    --texto-suave: #b8c0cc;
    --borda: #3d4652;
    --link: #9cc3ff;
    --foco: #9cc3ff;
    --alerta: #ffb4ab;
  }
}
* { box-sizing: border-box; }
html { background: var(--fundo); }
body {
  margin: 0;
  padding: 16px;
  background: var(--fundo);
  color: var(--texto);
  font: 16px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  overflow-wrap: anywhere;
}
h1 { font-size: 1.4rem; margin: 0 0 4px; }
h2 { font-size: 1rem; margin: 0 0 8px; }
h3 { font-size: 0.95rem; margin: 12px 0 6px; }
a { color: var(--link); }
a:focus-visible { outline: 3px solid var(--foco); outline-offset: 2px; }
.resumo, .dica-topo { margin: 0 0 4px; color: var(--texto-suave); }
.colunas {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 200px), 1fr));
  gap: 12px;
  align-items: start;
  margin-top: 16px;
}
.coluna {
  min-width: 0;
  background: var(--superficie);
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 10px;
}
.contagem { color: var(--texto-suave); font-weight: 400; }
.vazia, .resto { margin: 6px 0; font-size: 0.9rem; color: var(--texto-suave); }
.card {
  position: relative;
  min-width: 0;
  margin: 0 0 8px;
  padding: 8px 10px;
  background: var(--fundo);
  border: 1px solid var(--borda);
  border-radius: 6px;
}
.card:has(.card-link:focus-visible) { outline: 3px solid var(--foco); outline-offset: 2px; }
.titulo-cartao { font-size: 0.95rem; margin: 0 0 4px; }
.card-link { color: var(--texto); text-decoration: none; font-weight: 600; }
.card-link::after { content: ""; position: absolute; inset: 0; border-radius: 6px; }
.card-link:focus-visible { outline: none; }
.meta { margin: 2px 0; font-size: 0.85rem; color: var(--texto-suave); }
.detalhes { margin-top: 24px; }
.detalhe {
  display: none;
  max-width: 760px;
  margin: 0 0 16px;
  padding: 16px;
  background: var(--superficie);
  border: 1px solid var(--borda);
  border-radius: 8px;
  scroll-margin-top: 12px;
}
.detalhe:target { display: block; }
.detalhe h2:focus { outline: none; }
.detalhe h2:focus-visible { outline: 3px solid var(--foco); outline-offset: 2px; }
.topo-detalhe { margin: 0 0 4px; }
.fechar { font-size: 0.9rem; }
ol, ul { margin: 4px 0; padding-left: 20px; }
.recibo {
  margin: 4px 0;
  padding: 8px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 0.85rem;
  background: var(--fundo);
  border: 1px solid var(--borda);
  border-radius: 6px;
}
code { font-size: 0.9em; overflow-wrap: anywhere; }
</style>
</head>
<body>
<header>
<h1>Quadro da fábrica</h1>
<p class="resumo">@@RESUMO@@</p>
<p class="dica-topo">Clique em um cartão para ver etapas, arquivos, recibo e comentários. Esta página só mostra o estado: comentários e revisão são feitos pela CLI.</p>
</header>
<main class="colunas">
@@COLUNAS@@
</main>
<div class="detalhes">
@@DETALHES@@
</div>
<script>
(function () {
  window.addEventListener("hashchange", function () {
    var alvo = document.getElementById(location.hash.slice(1));
    if (alvo && alvo.classList.contains("detalhe")) {
      var titulo = alvo.querySelector("h2");
      if (titulo) { titulo.focus(); }
    }
  });
})();
</script>
</body>
</html>
