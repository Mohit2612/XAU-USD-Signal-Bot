package com.example.xausignalbot.ui.main

import android.content.Intent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation3.runtime.NavKey
import com.example.xausignalbot.BotService

@Composable
fun MainScreen(
  onItemClick: (NavKey) -> Unit,
  modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var isBotRunning by remember { mutableStateOf(false) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "🥇 XAU/USD Signal Bot",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )

        Card(
            modifier = Modifier.fillMaxWidth(),
            elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Status", style = MaterialTheme.typography.titleMedium)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Bot Engine: ", fontWeight = FontWeight.SemiBold)
                    Text(
                        text = if (isBotRunning) "Running 🟢" else "Stopped 🔴",
                        color = if (isBotRunning) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                    )
                }
            }
        }
        
        Card(
            modifier = Modifier.fillMaxWidth(),
            elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text("Bot Strategy Info", style = MaterialTheme.typography.titleMedium)
                
                Text("📌 Pair: XAU/USD (Gold Only)", fontWeight = FontWeight.SemiBold)
                Text("⏳ Timeframe: 15m & 1H Confluence")
                Text("📈 Strategy: SMC, VWAP, OTE Fibonacci")
                Text("🎯 Target R:R: 1:2.5 (Trailing SL enabled)")
                Text("🤖 Action: Auto Buy/Sell triggers sent to Telegram")
                
                Divider(modifier = Modifier.padding(vertical = 8.dp))
                
                Text(
                    text = "The bot analyzes real-time market data to find institutional trading zones. Once a setup is formed, signals are sent directly to your configured Telegram channel.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            Button(
                onClick = {
                    val intent = Intent(context, BotService::class.java)
                    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                        context.startForegroundService(intent)
                    } else {
                        context.startService(intent)
                    }
                    isBotRunning = true
                },
                enabled = !isBotRunning,
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
            ) {
                Text("Start Bot ▶")
            }

            Button(
                onClick = {
                    val intent = Intent(context, BotService::class.java)
                    context.stopService(intent)
                    isBotRunning = false
                },
                enabled = isBotRunning,
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
            ) {
                Text("Stop Bot ⏹")
            }
        }
        
        Spacer(modifier = Modifier.weight(1f))
    }
}

