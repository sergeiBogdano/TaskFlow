import test from 'node:test';
import assert from 'node:assert/strict';
import { clientFaviconUrl, clientContractSummary } from '../src/lib/clientPresentation.ts';
test('favicon uses the client site with no third-party service or page path', () => {
 assert.equal(clientFaviconUrl({domain:'https://example.org/team?a=1'}),'https://example.org/favicon.ico');
 assert.equal(clientFaviconUrl({domain:'пример.рф'}),'https://xn--e1afmkfd.xn--p1ai/favicon.ico');
});
test('missing and unsafe domains leave initials available', () => {
 for (const domain of ['', 'localhost', '127.0.0.1', 'https://user:pass@example.org', 'javascript://example.org', 'example.org:8080']) assert.equal(clientFaviconUrl({domain}),'');
});
test('placeholder client dates do not become a contract', () => {
 assert.deepEqual(clientContractSummary({contract_end:'2030-01-01',has_contract:false,contracts:[]}),{hasContract:false,end:''});
});
test('latest non-archived contract supplies its end date', () => {
 assert.deepEqual(clientContractSummary({contracts:[{status:'active',end_date:'2027-12-01'},{status:'archived',end_date:'2030-01-01'},{status:'active',end_date:'2028-01-01'}]}),{hasContract:true,end:'2028-01-01'});
});
test('restricted contract information is unknown, not a missing contract', () => {
 assert.deepEqual(clientContractSummary({has_contract:null,contracts:[],contract_end:'2030-01-01'}),{hasContract:null,end:''});
});
test('expired contracts remain present and can warn about their deadline', () => {
 assert.deepEqual(clientContractSummary({contracts:[{status:'expired',end_date:'2025-01-01'}]}),{hasContract:true,end:'2025-01-01'});
});
