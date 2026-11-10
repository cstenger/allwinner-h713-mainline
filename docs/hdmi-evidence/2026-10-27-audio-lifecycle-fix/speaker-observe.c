// SPDX-License-Identifier: GPL-2.0
/* Silent pre-roll and a bounded fade around the existing HDMI/codec route. */
#include <gst/gst.h>
#include <signal.h>

static volatile sig_atomic_t stopping;

static void stop_requested(int signum)
{
    (void)signum;
    stopping = 1;
}

static void fade_to(GstElement *volume, double from, double to, guint step_us)
{
    for (unsigned int i = 1; i <= 20; i++) {
        double t = (double)i / 20;
        g_object_set(volume, "volume", from + (to - from) * t * t, NULL);
        g_usleep(step_us);
        if (to > from && stopping)
            break;
    }
}

int main(int argc, char **argv)
{
    GstElement *pipeline, *volume;
    GstBus *bus;
    GstMessage *message;
    GstState state;
    GError *error = NULL;
    int result = 0;
    struct sigaction action = { .sa_handler = stop_requested };

    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    gst_init(&argc, &argv);
    pipeline = gst_parse_launch(
        "alsasrc device=hw:H713HDMI,0 buffer-time=40000 latency-time=10000 ! "
        "audio/x-raw,format=S16LE,rate=48000,channels=2 ! level name=input_level interval=1000000000 ! audioconvert ! "
        "audioresample ! volume name=startup_fade volume=0 ! "
        "level name=output_level interval=1000000000 ! alsasink device=plughw:Codec,0 buffer-time=80000 latency-time=10000",
        &error);
    if (!pipeline || error) {
        g_printerr("HDMI speaker pipeline: %s\n", error ? error->message : "creation failed");
        g_clear_error(&error);
        if (pipeline)
            gst_object_unref(pipeline);
        return 1;
    }
    volume = gst_bin_get_by_name(GST_BIN(pipeline), "startup_fade");
    bus = gst_element_get_bus(pipeline);
    if (gst_element_set_state(pipeline, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE ||
        gst_element_get_state(pipeline, &state, NULL, 5 * GST_SECOND) == GST_STATE_CHANGE_FAILURE ||
        state != GST_STATE_PLAYING) {
        g_printerr("HDMI speaker did not reach PLAYING; keeping silence\n");
        result = 1;
        goto cleanup;
    }
    /* The codec/amp power-up completes before PLAYING. Feed silence for at
     * least three output ring durations, then ramp the actual sample values. */
    g_usleep(300000);
    if (!stopping) {
        g_print("HDMI speaker ready; fading in after silent pre-roll\n");
        fade_to(volume, 0, 1, 25000);
    }
    while (!stopping) {
        message = gst_bus_timed_pop_filtered(bus, 100 * GST_MSECOND,
                                             GST_MESSAGE_ERROR | GST_MESSAGE_EOS | GST_MESSAGE_WARNING | GST_MESSAGE_ELEMENT);
        if (!message)
            continue;
        if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ELEMENT) {
            const GstStructure *st = gst_message_get_structure(message);
            gchar *text = st ? gst_structure_to_string(st) : g_strdup("no structure");
            g_print("LEVEL %s %s\n", GST_OBJECT_NAME(message->src), text);
            g_free(text); gst_message_unref(message); continue;
        }
        if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_WARNING) {
            gchar *detail = NULL;
            gst_message_parse_warning(message, &error, &detail);
            g_printerr("WARNING %s: %s %s\n", GST_OBJECT_NAME(message->src), error->message, detail ? detail : "");
            g_clear_error(&error); g_free(detail); gst_message_unref(message); continue;
        }
        if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR) {
            gst_message_parse_error(message, &error, NULL);
            g_printerr("HDMI speaker: %s\n", error->message);
            g_clear_error(&error);
        }
        /* A live route must not reach EOS. Let systemd restart the consumer. */
        result = 1;
        gst_message_unref(message);
        break;
    }
cleanup:
    /* Silence the running ring before closing; keep codec power sequencing
     * and external amplifier GPIO ownership in the existing ASoC driver. */
    {
        double current = 0;
        g_object_get(volume, "volume", &current, NULL);
        fade_to(volume, current, 0, 5000);
    }
    g_object_set(volume, "volume", 0.0, NULL);
    g_usleep(100000);
    gst_element_set_state(pipeline, GST_STATE_NULL);
    gst_object_unref(bus);
    gst_object_unref(volume);
    gst_object_unref(pipeline);
    return result;
}
