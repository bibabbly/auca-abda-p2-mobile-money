# Dot-source in each new PowerShell window before using Neo4j:
#   . D:\AUCA\ABDA_Project2\neo4j_env.ps1
# Uses the Java 21 runtime bundled with Neo4j Desktop (system Java is 17, too old for Neo4j 2026).
$env:JAVA_HOME = "$env:USERPROFILE\.Neo4jDesktop2\Cache\runtime\zulu21.50.19-ca-jre21.0.11-win_x64"
$env:NEO4J_HOME = "D:\AUCA\neo4j-community"
$env:Path = "$env:NEO4J_HOME\bin;$env:JAVA_HOME\bin;$env:Path"
Write-Host "JAVA_HOME  = $env:JAVA_HOME"
Write-Host "NEO4J_HOME = $env:NEO4J_HOME"
