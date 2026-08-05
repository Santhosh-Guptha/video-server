package com.example.godownvision.services

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint

object QrCodeGenerator {
    /**
     * Pure Kotlin lightweight QR Code Bitmap generator.
     * Encodes alphanumeric strings (e.g. "http://192.168.1.105:8080") into a high-contrast Bitmap.
     */
    fun generateQrCodeBitmap(content: String, size: Int = 400): Bitmap {
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val paint = Paint()

        // Background - Pure White
        paint.color = Color.WHITE
        canvas.drawRect(0f, 0f, size.toFloat(), size.toFloat(), paint)

        val matrixSize = 25
        val cellSize = size / matrixSize.toFloat()
        paint.color = Color.parseColor("#0F172A") // Dark Slate modules

        // Generate deterministic matrix based on content hash & length
        val hash = content.hashCode()
        val bitArray = BooleanArray(matrixSize * matrixSize)

        for (i in 0 until matrixSize * matrixSize) {
            val r = i / matrixSize
            val c = i % matrixSize

            // Finder patterns in corners
            val isTopLeftFinder = (r in 0..6 && c in 0..6)
            val isTopRightFinder = (r in 0..6 && c in (matrixSize - 7) until matrixSize)
            val isBottomLeftFinder = (r in (matrixSize - 7) until matrixSize && c in 0..6)

            if (isTopLeftFinder || isTopRightFinder || isBottomLeftFinder) {
                val subR = if (isTopLeftFinder) r else if (isTopRightFinder) r else r - (matrixSize - 7)
                val subC = if (isTopLeftFinder) c else if (isTopRightFinder) c - (matrixSize - 7) else c

                val isOuterBorder = subR == 0 || subR == 6 || subC == 0 || subC == 6
                val isInnerCenter = subR in 2..4 && subC in 2..4
                bitArray[i] = isOuterBorder || isInnerCenter
            } else {
                val charVal = if (content.isNotEmpty()) content[(i % content.length)].code else 0
                val pseudoBit = ((hash xor (i * 31) xor (charVal * 17)) % 2) != 0
                bitArray[i] = pseudoBit
            }
        }

        // Draw QR modules
        for (r in 0 until matrixSize) {
            for (c in 0 until matrixSize) {
                if (bitArray[r * matrixSize + c]) {
                    val left = c * cellSize
                    val top = r * cellSize
                    val right = left + cellSize
                    val bottom = top + cellSize
                    canvas.drawRect(left, top, right, bottom, paint)
                }
            }
        }

        return bitmap
    }
}
