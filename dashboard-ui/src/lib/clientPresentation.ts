type ClientSummary = { domain?: string; has_contract?: boolean | null; contract_end?: string; contracts?: { status?: string; end_date?: string }[] };
export function clientFaviconUrl(client: ClientSummary | null | undefined): string {
  if (!client?.domain?.trim()) return '';
  try {
    const domain = client.domain.trim();
    const url = new URL(domain.includes('://') ? domain : `https://${domain}`);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.port) return '';
    const host = url.hostname.toLowerCase();
    if (!host.includes('.') || host.endsWith('.local') || host.endsWith('.localhost') || host.includes(':') || /^\d+\.\d+\.\d+\.\d+$/.test(host)) return '';
    return `https://${host}/favicon.ico`;
  } catch { return ''; }
}
export function clientContractSummary(client: ClientSummary | null | undefined) {
  if (!client || client.has_contract === null) return { hasContract: null, end: '' };
  const contracts = client.contracts?.filter(contract => !['archived', 'closed'].includes(contract.status || 'active'));
  const hasContract = client.has_contract ?? (contracts ? contracts.length > 0 : Boolean(client.contract_end));
  const end = hasContract ? (contracts?.map(contract => contract.end_date || '').filter(Boolean).sort().at(-1) || client.contract_end || '') : '';
  return { hasContract, end };
}
