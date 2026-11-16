# Open the report in Microsoft Word, refresh the table of contents and fields, save, export PDF.
param([Parameter(Mandatory = $true)][string]$Path)
$full = (Resolve-Path $Path).Path
$pdf = [System.IO.Path]::ChangeExtension($full, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($full)
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Fields.Update() | Out-Null
    $doc.Save()
    $doc.ExportAsFixedFormat($pdf, 17)   # 17 = wdExportFormatPDF
    "pages: " + $doc.ComputeStatistics(2)  # 2 = wdStatisticPages
    $doc.Close($false)
    "saved: $full"
    "pdf:   $pdf"
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
