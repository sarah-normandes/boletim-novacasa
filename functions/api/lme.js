/* Coleta das cotações da LME no servidor do Cloudflare Pages.
   Rota gerada automaticamente pelo caminho do arquivo: /api/lme
   O painel chama esse endereço no próprio domínio, sem bloqueio de
   origem cruzada e sem proxies de terceiros. */

const MESES = {jan:1,fev:2,mar:3,abr:4,mai:5,jun:6,jul:7,ago:8,set:9,out:10,nov:11,dez:12};

const limpar = s => s
  .replace(/<[^>]*>/g, " ")
  .replace(/&nbsp;/gi, " ")
  .replace(/&amp;/gi, "&")
  .replace(/\s+/g, " ")
  .trim();

function numero(txt, decimalVirgula){
  let s = String(txt).replace(/[^\d.,-]/g, "");
  if(!s) return NaN;
  s = decimalVirgula ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  return parseFloat(s);
}

function extrair(html, ano, mes){
  const dias = [];
  const tabelas = html.match(/<table[\s\S]*?<\/table>/gi) || [];
  for(const tabela of tabelas){
    const linhas = tabela.match(/<tr[\s\S]*?<\/tr>/gi) || [];
    let iCobre = -1, iDolar = -1;

    for(const linha of linhas){
      const celulas = (linha.match(/<t[dh][^>]*>[\s\S]*?<\/t[dh]>/gi) || []).map(limpar);
      if(!celulas.length) continue;

      if(iCobre < 0){
        const baixa = celulas.map(c => c.toLowerCase());
        iCobre = baixa.findIndex(c => c.includes("cobre"));
        iDolar = baixa.findIndex(c => c.includes("lar"));
        continue;
      }
      if(celulas.length <= Math.max(iCobre, iDolar)) continue;

      const rotulo = celulas[0].toLowerCase();
      if(/m[eé]dia|total/.test(rotulo)) continue;
      const m = rotulo.match(/^(\d{1,2})\/([a-zç]{3})/);
      if(!m || !MESES[m[2]] || MESES[m[2]] !== mes) continue;

      const cobre = numero(celulas[iCobre], false);
      const dolar = numero(celulas[iDolar], true);
      if(cobre > 0 && dolar > 0){
        dias.push([`${ano}-${String(mes).padStart(2,"0")}-${m[1].padStart(2,"0")}`, cobre, dolar]);
      }
    }
    if(dias.length) break;
  }
  return dias;
}

export async function onRequest(context){
  const url = new URL(context.request.url);
  const hoje = new Date();
  const ano = Number(url.searchParams.get("ano")) || hoje.getFullYear();
  const ateMes = ano === hoje.getFullYear() ? hoje.getMonth() + 1 : 12;
  const desdeMes = Number(url.searchParams.get("desde")) || 1;

  const alvos = [];
  for(let m = desdeMes; m <= ateMes; m++) alvos.push(m);

  const lotes = await Promise.all(alvos.map(async m => {
    try{
      const r = await fetch(`https://shockmetais.com.br/lme/${m}-${ano}`, {
        headers: {"user-agent": "Mozilla/5.0 (painel-cobre)"}
      });
      if(!r.ok) return [];
      return extrair(await r.text(), ano, m);
    }catch(e){
      return [];
    }
  }));

  const mapa = new Map();
  lotes.flat().forEach(d => mapa.set(d[0], d));
  const dias = [...mapa.values()].sort((a,b) => a[0] < b[0] ? -1 : 1);

  return new Response(JSON.stringify({
    fonte: "shockmetais.com.br/lme",
    ano,
    atualizado: new Date().toISOString(),
    total: dias.length,
    dias
  }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
      "cache-control": "public, max-age=600, s-maxage=600"
    }
  });
}
