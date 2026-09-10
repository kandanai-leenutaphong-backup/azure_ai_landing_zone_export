using '../main.bicep'

param location = 'southeastasia'
// Set these to different subscription IDs for a cross-subscription topology.
// If omitted, both default to the subscription where the deployment is started.
param hubSubscriptionId = '1b00124c-ed9b-4d33-9bd6-4d14c09c9857'
param spokeSubscriptionId = 'd88c020a-2180-43da-91a2-f6cc01f25946'
param hubResourceGroupName = 'rg-hub-sea'
param spokeResourceGroupName = 'rg-ai-dev-sea'

// AI Gateway Landing Zone subscription (APIM, hub Foundry, Managed Redis semantic
// cache, usage/chargeback pipeline). See docs/ai-gateway-landing-zone.md.
param deployAiGateway = true
param aiGatewaySubscriptionId = '0d04b43f-7d15-40fd-8aa5-830f71ab0d80'
param aiGatewayResourceGroupName = 'rg-ai-gateway-sea'
param apimPublisherEmail = 'ai-gateway-admin@contoso.com'
param entraAudience = 'e9de7c75-a166-4030-8c05-81694cc1fecb'
param deployFoundryAppInsightsRoleAssignments = false
param aiGatewayDepartments = [
  {
    name: 'odi'
    displayName: 'ODI'
  }
  {
    name: 'fa'
    displayName: 'Finance & Analytics'
  }
]

param enableBastion = false
param vpnGatewayName = 'hub-VNetGw-sea-dev'
param p2sClientAddressPool = '172.16.0.0/24'
param dnsResolverInboundIp = '10.0.2.4'
param enableMdeExtension = false
param enableComputerVision = false
param appImageTag = 'latest'
param deployRepositoryApps = true
param deployThaiSurnameApp = true
param enableThaiPublicGateway = true
param sqlEntraAdminLogin = 'kandanail@MngEnvMCAP953893.onmicrosoft.com'
param sqlEntraAdminObjectId = 'c0e5e079-b4b0-441b-9fe6-a91dda52b29c'

// Paste the real, existing SSH public keys for myVm and vm-2 before deploying.
// These are secrets — do not commit real values to source control; supply them via
// --parameters at deploy time or a secure parameter store instead.
param sshPublicKeyVm1 = 'ssh-rsa AAAA... REPLACE_ME vm-1-key'
param sshPublicKeyVm2 = 'ssh-rsa AAAA... REPLACE_ME vm-2-key'

param tags = {
  environment: 'exported'
  source: 'rg-vnet-hub-2 + rg-vm-vnet-test + rg-foundry-standard-private-westus3'
}
