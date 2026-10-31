# Builds networking outreach drafts in classic Outlook from drafts.json and bodies\*.html. NEVER sends: only .Save().
# Outlook inserts your own signature (GetInspector), and each body is placed above it. Reply mode threads on your sent message.
param([string]$Only, [switch]$WhatIf, [switch]$Force)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$list = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'drafts.json') | ConvertFrom-Json
if ($Only) { $list = @($list | Where-Object { $_.key -eq $Only }) }
$o = New-Object -ComObject Outlook.Application
$ns = $o.GetNamespace('MAPI')
$drafts = $ns.GetDefaultFolder(16)
$sent = $ns.GetDefaultFolder(5)
$PR = 'http://schemas.microsoft.com/mapi/proptag/0x39FE001E'
function Smtp($r) { try { $r.PropertyAccessor.GetProperty($PR) } catch { $r.Address } }
function Insert-Body($item, $snippet) {
  $null = $item.GetInspector          # makes Outlook add the user's own signature
  $h = $item.HTMLBody
  $m = [regex]::Match($h, '<body[^>]*>', 'IgnoreCase')
  if ($m.Success) { $item.HTMLBody = $h.Substring(0, $m.Index + $m.Length) + $snippet + $h.Substring($m.Index + $m.Length) }
  else { $item.HTMLBody = "<html><body>$snippet</body></html>" + $h }
}
function Marker($html) { $t = ($html -replace '<[^>]+>', ' ' -replace '&amp;', '&' -replace '\s+', ' ').Trim(); $t.Substring(0, [Math]::Min(60, $t.Length)) }
$made = 0
foreach ($d in $list) {
  $snippet = Get-Content -Raw -Encoding UTF8 (Join-Path $root ('bodies\' + $d.file))
  $marker = Marker $snippet
  $dup = $false
  foreach ($x in @($drafts.Items)) {
    if ($x.Body -and $x.Body.Replace("`r", '').Replace("`n", ' ') -like ('*' + $marker.Substring(0, [Math]::Min(40, $marker.Length)) + '*')) {
      $addrs = @(); foreach ($r in $x.Recipients) { $addrs += (Smtp $r) }
      if (-not $d.to -or ($addrs -contains $d.to)) { $dup = $true; break }
    }
  }
  if ($dup -and -not $Force) { "SKIP (draft exists): $($d.key)"; continue }
  if ($WhatIf) { "WOULD BUILD: $($d.key) -> $($d.to) [$($d.mode)]"; continue }
  if ($d.mode -eq 'Reply') {
    $esc = $d.reply_to -replace "'", "''"
    $c = $sent.Items.Restrict("@SQL=""urn:schemas:httpmail:subject"" LIKE '%$esc%'")
    $c.Sort('[SentOn]', $true)
    $orig = $null
    foreach ($s in $c) { foreach ($r in $s.Recipients) { if ((Smtp $r) -ieq $d.to) { $orig = $s; break } }; if ($orig) { break } }
    if (-not $orig) { "SKIP (no sent message to reply to): $($d.key)"; continue }
    $item = $orig.Reply()
    while ($item.Recipients.Count -gt 0) { $item.Recipients.Remove(1) }
    [void]$item.Recipients.Add($d.to).Resolve()
    $null = $item.GetInspector
    $h = $item.HTMLBody
    $m = [regex]::Match($h, '<body[^>]*>', 'IgnoreCase')
    $item.HTMLBody = $h.Substring(0, $m.Index + $m.Length) + $snippet + $h.Substring($m.Index + $m.Length)
  } else {
    $item = $o.CreateItem(0)
    $item.Subject = $d.subject
    if ($d.to) { [void]$item.Recipients.Add($d.to).Resolve() }
    Insert-Body $item $snippet
  }
  $item.Save()
  $made++
  "BUILT: $($d.key) -> $(if ($d.to) { $d.to } else { '(no address yet)' }) | $($item.Subject)"
}
"Drafts built: $made (nothing sent)"
