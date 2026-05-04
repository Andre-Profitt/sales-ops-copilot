<# Read latest PP crash event detail. #>
$ErrorActionPreference = "Continue"
Get-EventLog -LogName Application -Newest 5 -EntryType Error -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -in @("Application Error", "Microsoft Office 16") } |
    Select-Object -First 3 TimeGenerated, Source, EventID, Message |
    ForEach-Object {
        Write-Output "=== $($_.TimeGenerated) | $($_.Source) | $($_.EventID) ==="
        Write-Output ($_.Message.Substring(0, [Math]::Min(800, $_.Message.Length)))
        Write-Output ""
    }
