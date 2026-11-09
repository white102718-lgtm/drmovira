package com.adpulse.system.notification.controller;

import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.notification.service.SiteNotificationStreamService;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** 站内通知实时事件流。 */
@RestController
@RequestMapping("/asset-flow-v2/notifications")
public class SiteNotificationStreamController {
    private final SiteNotificationStreamService streamService;

    public SiteNotificationStreamController(SiteNotificationStreamService streamService) {
        this.streamService = streamService;
    }

    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<SseEmitter> stream(
            @RequestHeader(value = "Last-Event-ID", required = false) String lastEventId) {
        SseEmitter emitter =
                streamService.subscribe(
                        SecurityContextHelper.currentUser(), parseLastEventId(lastEventId));
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .header("X-Accel-Buffering", "no")
                .body(emitter);
    }

    private Long parseLastEventId(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            long parsed = Long.parseLong(value);
            return parsed >= 0 ? parsed : null;
        } catch (NumberFormatException ignored) {
            return null;
        }
    }
}
