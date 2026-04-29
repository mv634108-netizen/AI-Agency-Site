<?php
/**
 * Скрипт отправки заявок в Telegram
 * Настроен для Telegram Bot Token: 8782399425:AAHN4zbUNSydDARqkm4L3lyJ3BgJfECN0kI
 * Настроен для Chat ID: 8001698573
 */

header('Content-Type: application/json');

// --- НАСТРОЙКИ ---
$token = "8782399425:AAHN4zbUNSydDARqkm4L3lyJ3BgJfECN0kI"; 
$chat_id = "8001698573";   

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    $name = isset($_POST['name']) ? strip_tags($_POST['name']) : 'Не указано';
    $phone = isset($_POST['phone']) ? strip_tags($_POST['phone']) : 'Не указано';
    $niche = "Сайт + Яндекс.Директ + Telegram (24ч)";

    // Формируем текст сообщения
    $message = "🚀 **НОВАЯ ЗАЯВКА С САЙТА**\n\n";
    $message .= "👤 **Имя:** {$name}\n";
    $message .= "📞 **Телефон:** {$phone}\n";
    $message .= "💼 **Услуга:** {$niche}\n";
    $message .= "\n🌐 **Источник:** Cyber AI System";

    // Отправка в Telegram через cURL
    $url = "https://api.telegram.org/bot{$token}/sendMessage";
    $data = [
        'chat_id' => $chat_id,
        'text' => $message,
        'parse_mode' => 'Markdown'
    ];

    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($data));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    
    $response = curl_exec($ch);
    $error = curl_error($ch);
    curl_close($ch);

    if ($error) {
        echo json_encode(['status' => 'error', 'message' => 'Ошибка сервера: ' . $error]);
    } else {
        $res = json_decode($response, true);
        if (isset($res['ok']) && $res['ok']) {
            echo json_encode(['status' => 'success', 'message' => 'Заявка успешно отправлена!']);
        } else {
            $desc = isset($res['description']) ? $res['description'] : 'Ошибка API';
            echo json_encode(['status' => 'error', 'message' => 'Ошибка Telegram: ' . $desc]);
        }
    }
} else {
    echo json_encode(['status' => 'error', 'message' => 'Доступ запрещен']);
}
?>
