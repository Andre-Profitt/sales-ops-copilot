<#
Send probe requests to app.prod.ai.think-cell.com/core/ from the Windows VM
where think-cell is installed. If VM gets 200/401/400 vs Mac's 403, the
rejection is IP/geo based and must be sent from a "real client" IP.
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\tc_core_probe.log" -Force | Out-Null

$urls = @(
    "https://app.prod.ai.think-cell.com/",
    "https://app.prod.ai.think-cell.com/core/",
    "https://app.prod.ai.think-cell.com/core/chat/completions",
    "https://aiauthentication.appcom.think-cell.com/"
)
foreach ($u in $urls) {
    try {
        $resp = Invoke-WebRequest -Uri $u -Method Get -TimeoutSec 10 -UseBasicParsing -Headers @{ 'User-Agent' = 'think-cell/1000220' } -ErrorAction Stop
        $body = if ($resp.Content) { $resp.Content.ToString().Substring(0, [Math]::Min(200, $resp.Content.ToString().Length)) } else { '' }
        Write-Output "[$($resp.StatusCode)] GET $u"
        Write-Output "  via=$($resp.Headers.'Via') server=$($resp.Headers.Server)"
        Write-Output "  body=$body"
    } catch [System.Net.WebException] {
        $r = $_.Exception.Response
        if ($r) {
            $stream = $r.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $body = $reader.ReadToEnd()
            $body = $body.Substring(0, [Math]::Min(300, $body.Length))
            Write-Output "[$([int]$r.StatusCode) $($r.StatusDescription)] GET $u"
            Write-Output "  server=$($r.Headers['Server']) via=$($r.Headers['Via'])"
            Write-Output "  body=$body"
        } else {
            Write-Output "  EXCEPTION GET $($u): $($_.Exception.Message)"
        }
    } catch {
        Write-Output "  ERROR GET $($u): $($_.Exception.Message)"
    }
    Write-Output ""
}

Stop-Transcript | Out-Null
