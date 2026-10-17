// cassandra-gui.cpp — Interface gráfica para Cassandra Agent (Linux/GTK4)
// Compilar: g++ -std=c++20 -O2 cassandra-gui.cpp -o cassandra-gui \
//           $(pkg-config --cflags --libs gtk4 libadwaita-1) -lpthread

#include <gtk/gtk.h>
#include <adwaita.h>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <condition_variable>
#include <mutex>
#include <queue>

constexpr int WINDOW_WIDTH  = 1100;
constexpr int WINDOW_HEIGHT = 720;

struct ChatMessage {
    std::string role;
    std::string content;
    std::string timestamp;
};

static GtkWidget         *g_main_window   = nullptr;
static GtkWidget         *g_chat_listbox  = nullptr;
static GtkTextBuffer     *g_input_buffer  = nullptr;
static GtkWidget         *g_status_label  = nullptr;
static GtkWidget         *g_model_label   = nullptr;
static GtkWidget         *g_send_button   = nullptr;
static GtkWidget         *g_stop_button   = nullptr;
static GtkWidget         *g_clear_button  = nullptr;
static GtkWidget         *g_config_button = nullptr;
static GtkWidget         *g_config_revealer = nullptr;
static GtkWidget         *g_api_key_entry = nullptr;
static GtkWidget         *g_provider_drop = nullptr;
static GtkWidget         *g_model_entry   = nullptr;

static std::vector<ChatMessage>     g_messages;
static std::atomic<bool>            g_running{false};
static std::atomic<bool>            g_generating{false};
static std::mutex                   g_queue_mutex;
static std::condition_variable      g_queue_cv;
static std::queue<std::function<void()>> g_ui_queue;

static std::string g_api_key;
static std::string g_provider = "openai";
static std::string g_model    = "gpt-4o";
static std::string g_base_url = "https://api.openai.com/v1";

static std::string now_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto t   = std::chrono::system_clock::to_time_t(now);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%H:%M", std::localtime(&t));
    return std::string(buf);
}

static void queue_ui(std::function<void()> fn) {
    {
        std::lock_guard<std::mutex> lk(g_queue_mutex);
        g_ui_queue.push(std::move(fn));
    }
    g_queue_cv.notify_one();
}

static gboolean drain_ui_queue(gpointer) {
    std::queue<std::function<void()>> local;
    {
        std::lock_guard<std::mutex> lk(g_queue_mutex);
        std::swap(local, g_ui_queue);
    }
    while (!local.empty()) {
        local.front()();
        local.pop();
    }
    return G_SOURCE_CONTINUE;
}

static const char *CSS = R"CSS(
window { background: #0d1117; }
.headerbar { background: #161b22; border-bottom: 1px solid #21262d; min-height: 56px; }
.sidebar { background: #0d1117; border-right: 1px solid #21262d; }
.sidebar-label { color: #8b949e; font-size: 11px; font-weight: 600; letter-spacing: 0.5px; padding: 16px 16px 6px 16px; }
.sidebar-item { padding: 8px 16px; border-radius: 6px; margin: 1px 8px; color: #c9d1d9; font-size: 13px; transition: background 0.15s; }
.sidebar-item:hover { background: #161b22; }
.sidebar-item.active { background: #1f6feb; color: #ffffff; }
.chat-area { background: #0d1117; }
.msg-user { background: #1f6feb; color: #ffffff; border-radius: 16px 16px 4px 16px; padding: 10px 14px; margin: 4px 0 4px 60px; font-size: 14px; line-height: 1.5; }
.msg-cassandra { background: #161b22; color: #c9d1d9; border: 1px solid #21262d; border-radius: 16px 16px 16px 4px; padding: 10px 14px; margin: 4px 60px 4px 0; font-size: 14px; line-height: 1.5; }
.msg-system { background: #21262d; color: #8b949e; border-radius: 8px; padding: 6px 12px; margin: 4px 40px; font-size: 12px; font-style: italic; }
.msg-timestamp { color: #484f58; font-size: 10px; margin-top: 2px; }
.input-area { background: #161b22; border-top: 1px solid #21262d; }
.input-textview { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 8px; padding: 8px 12px; font-size: 14px; font-family: 'JetBrains Mono', 'Fira Code', monospace; }
.input-textview:focus { border-color: #1f6feb; box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.3); }
.btn-primary { background: #1f6feb; color: #ffffff; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600; border: none; transition: background 0.15s; }
.btn-primary:hover { background: #388bfd; }
.btn-primary:disabled { background: #21262d; color: #484f58; }
.btn-danger { background: #da3633; color: #ffffff; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600; border: none; }
.btn-danger:hover { background: #f85149; }
.btn-ghost { background: transparent; color: #8b949e; border: 1px solid #30363d; border-radius: 8px; padding: 8px 16px; font-size: 13px; transition: all 0.15s; }
.btn-ghost:hover { background: #21262d; color: #c9d1d9; }
.status-bar { background: #161b22; border-top: 1px solid #21262d; padding: 4px 16px; }
.status-dot { border-radius: 50%; min-width: 8px; min-height: 8px; }
.status-online { background: #3fb950; box-shadow: 0 0 6px rgba(63, 185, 80, 0.5); }
.status-offline { background: #484f58; }
.status-busy { background: #d29922; box-shadow: 0 0 6px rgba(210, 153, 34, 0.5); }
.config-panel { background: #161b22; border-right: 1px solid #21262d; }
.config-entry { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 6px 10px; font-size: 13px; }
.config-entry:focus { border-color: #1f6feb; }
.config-label { color: #8b949e; font-size: 11px; font-weight: 600; margin-bottom: 4px; }
.title-label { color: #f0f6fc; font-size: 16px; font-weight: 700; letter-spacing: -0.3px; }
.subtitle-label { color: #8b949e; font-size: 12px; }
.model-badge { background: #21262d; color: #58a6ff; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-family: monospace; }
.empty-state { color: #484f58; font-size: 14px; }
.scrollbar { background: transparent; }
scrollbar slider { background: #30363d; border-radius: 4px; min-width: 6px; min-height: 6px; }
scrollbar slider:hover { background: #484f58; }
)CSS";

static GtkWidget* create_message_row(const ChatMessage &msg) {
    GtkWidget *row  = gtk_box_new(GTK_ORIENTATION_VERTICAL, 2);
    gtk_widget_set_margin_start(row, 12);
    gtk_widget_set_margin_end(row, 12);
    gtk_widget_set_margin_top(row, 2);
    gtk_widget_set_margin_bottom(row, 2);

    GtkWidget *bubble = gtk_label_new(msg.content.c_str());
    gtk_label_set_wrap(GTK_LABEL(bubble), TRUE);
    gtk_label_set_xalign(GTK_LABEL(bubble), 0.0f);
    gtk_label_set_yalign(GTK_LABEL(bubble), 0.0f);
    gtk_widget_set_halign(bubble, msg.role == "user" ? GTK_ALIGN_END : GTK_ALIGN_START);

    std::string css_class;
    if (msg.role == "user")       css_class = "msg-user";
    else if (msg.role == "cassandra") css_class = "msg-cassandra";
    else                          css_class = "msg-system";

    gtk_widget_add_css_class(bubble, css_class.c_str());

    GtkWidget *ts = gtk_label_new(msg.timestamp.c_str());
    gtk_widget_add_css_class(ts, "msg-timestamp");
    gtk_widget_set_halign(ts, msg.role == "user" ? GTK_ALIGN_END : GTK_ALIGN_START);

    gtk_box_append(GTK_BOX(row), bubble);
    gtk_box_append(GTK_BOX(row), ts);
    return row;
}

static void refresh_chat() {
    if (!g_chat_listbox) return;

    GtkWidget *child = gtk_widget_get_first_child(g_chat_listbox);
    while (child) {
        GtkWidget *next = gtk_widget_get_next_sibling(child);
        gtk_list_box_remove(GTK_LIST_BOX(g_chat_listbox), child);
        child = next;
    }

    if (g_messages.empty()) {
        GtkWidget *empty = gtk_label_new("Nenhuma mensagem ainda.\nDigite algo abaixo para começar.");
        gtk_widget_add_css_class(empty, "empty-state");
        gtk_list_box_append(GTK_LIST_BOX(g_chat_listbox), empty);
        return;
    }

    for (const auto &msg : g_messages) {
        gtk_list_box_append(GTK_LIST_BOX(g_chat_listbox), create_message_row(msg));
    }

    GtkAdjustment *adj = gtk_scrolled_window_get_vadjustment(
        GTK_SCROLLED_WINDOW(gtk_widget_get_parent(g_chat_listbox)));
    if (adj) {
        gtk_adjustment_set_value(adj, gtk_adjustment_get_upper(adj));
    }
}

static void add_message(const std::string &role, const std::string &content) {
    ChatMessage msg;
    msg.role      = role;
    msg.content   = content;
    msg.timestamp = now_timestamp();
    g_messages.push_back(std::move(msg));
    queue_ui([]{ refresh_chat(); });
}

static void set_status(const std::string &text, bool online, bool busy) {
    queue_ui([text, online, busy]{
        if (g_status_label) gtk_label_set_text(GTK_LABEL(g_status_label), text.c_str());
        GtkWidget *dot = gtk_widget_get_prev_sibling(g_status_label);
        if (dot) {
            gtk_widget_remove_css_class(dot, "status-online");
            gtk_widget_remove_css_class(dot, "status-offline");
            gtk_widget_remove_css_class(dot, "status-busy");
            if (busy)       gtk_widget_add_css_class(dot, "status-busy");
            else if (online) gtk_widget_add_css_class(dot, "status-online");
            else            gtk_widget_add_css_class(dot, "status-offline");
        }
    });
}

static void set_generating(bool gen) {
    g_generating = gen;
    queue_ui([gen]{
        if (g_send_button) gtk_widget_set_sensitive(g_send_button, !gen);
        if (g_stop_button) gtk_widget_set_sensitive(g_stop_button, gen);
    });
}

static void on_send_clicked(GtkButton*, gpointer) {
    if (g_generating) return;

    GtkTextIter start, end;
    gtk_text_buffer_get_bounds(g_input_buffer, &start, &end);
    char *text = gtk_text_buffer_get_text(g_input_buffer, &start, &end, FALSE);
    std::string prompt(text);
    g_free(text);

    if (prompt.empty()) return;

    gtk_text_buffer_set_text(g_input_buffer, "", -1);
    add_message("user", prompt);
    set_generating(true);
    set_status("Gerando resposta...", true, true);

    std::thread([prompt]{
        std::this_thread::sleep_for(std::chrono::milliseconds(800));
        std::string resposta = "Resposta simulada para: " + prompt;
        add_message("cassandra", resposta);
        set_generating(false);
        set_status("Pronto", true, false);
    }).detach();
}

static void on_stop_clicked(GtkButton*, gpointer) {
    set_generating(false);
    set_status("Interrompido", true, false);
}

static void on_clear_clicked(GtkButton*, gpointer) {
    g_messages.clear();
    refresh_chat();
}

static void on_config_clicked(GtkButton*, gpointer) {
    gboolean revealed = gtk_revealer_get_reveal_child(GTK_REVEALER(g_config_revealer));
    gtk_revealer_set_reveal_child(GTK_REVEALER(g_config_revealer), !revealed);
}

static void on_save_config(GtkButton*, gpointer) {
    const char *key = gtk_editable_get_text(GTK_EDITABLE(g_api_key_entry));
    g_api_key = key ? key : "";

    const char *model = gtk_editable_get_text(GTK_EDITABLE(g_model_entry));
    g_model = model ? model : "gpt-4o";

    if (g_model_label) {
        gtk_label_set_text(GTK_LABEL(g_model_label), g_model.c_str());
    }

    gtk_revealer_set_reveal_child(GTK_REVEALER(g_config_revealer), FALSE);
    set_status("Configuração salva", true, false);
}

static void build_sidebar(GtkWidget *parent) {
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_add_css_class(box, "sidebar");

    GtkWidget *logo_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 2);
    gtk_widget_set_margin_top(logo_box, 20);
    gtk_widget_set_margin_bottom(logo_box, 20);
    gtk_widget_set_margin_start(logo_box, 16);
    gtk_widget_set_margin_end(logo_box, 16);

    GtkWidget *title = gtk_label_new("CASSANDRA");
    gtk_widget_add_css_class(title, "title-label");
    gtk_label_set_xalign(GTK_LABEL(title), 0.0f);

    GtkWidget *subtitle = gtk_label_new("Offensive Security Agent");
    gtk_widget_add_css_class(subtitle, "subtitle-label");
    gtk_label_set_xalign(GTK_LABEL(subtitle), 0.0f);

    gtk_box_append(GTK_BOX(logo_box), title);
    gtk_box_append(GTK_BOX(logo_box), subtitle);
    gtk_box_append(GTK_BOX(box), logo_box);

    GtkWidget *sep = gtk_separator_new(GTK_ORIENTATION_HORIZONTAL);
    gtk_widget_set_margin_top(sep, 8);
    gtk_widget_set_margin_bottom(sep, 8);
    gtk_box_append(GTK_BOX(box), sep);

    GtkWidget *label = gtk_label_new("CONVERSA");
    gtk_widget_add_css_class(label, "sidebar-label");
    gtk_label_set_xalign(GTK_LABEL(label), 0.0f);
    gtk_box_append(GTK_BOX(box), label);

    const char *items[] = {"Chat Principal", "Histórico", "Configurações"};
    for (int i = 0; i < 3; i++) {
        GtkWidget *item = gtk_label_new(items[i]);
        gtk_widget_add_css_class(item, "sidebar-item");
        if (i == 0) gtk_widget_add_css_class(item, "active");
        gtk_label_set_xalign(GTK_LABEL(item), 0.0f);
        gtk_box_append(GTK_BOX(box), item);
    }

    GtkWidget *spacer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_vexpand(spacer, TRUE);
    gtk_box_append(GTK_BOX(box), spacer);

    GtkWidget *status_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_widget_set_margin_top(status_box, 12);
    gtk_widget_set_margin_bottom(status_box, 16);
    gtk_widget_set_margin_start(status_box, 16);
    gtk_widget_set_margin_end(status_box, 16);

    GtkWidget *dot = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_add_css_class(dot, "status-dot");
    gtk_widget_add_css_class(dot, "status-online");

    GtkWidget *status = gtk_label_new("Online");
    gtk_widget_add_css_class(status, "subtitle-label");

    gtk_box_append(GTK_BOX(status_box), dot);
    gtk_box_append(GTK_BOX(status_box), status);
    gtk_box_append(GTK_BOX(box), status_box);

    gtk_box_append(GTK_BOX(parent), box);
}

static void build_config_panel(GtkWidget *parent) {
    GtkWidget *panel = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12);
    gtk_widget_add_css_class(panel, "config-panel");
    gtk_widget_set_size_request(panel, 240, -1);
    gtk_widget_set_margin_top(panel, 20);
    gtk_widget_set_margin_bottom(panel, 20);
    gtk_widget_set_margin_start(panel, 16);
    gtk_widget_set_margin_end(panel, 16);

    GtkWidget *title = gtk_label_new("Configurações");
    gtk_widget_add_css_class(title, "title-label");
    gtk_label_set_xalign(GTK_LABEL(title), 0.0f);
    gtk_box_append(GTK_BOX(panel), title);

    GtkWidget *key_label = gtk_label_new("API KEY");
    gtk_widget_add_css_class(key_label, "config-label");
    gtk_label_set_xalign(GTK_LABEL(key_label), 0.0f);
    gtk_box_append(GTK_BOX(panel), key_label);

    g_api_key_entry = gtk_entry_new();
    gtk_widget_add_css_class(g_api_key_entry, "config-entry");
    gtk_entry_set_placeholder_text(GTK_ENTRY(g_api_key_entry), "sk-...");
    gtk_entry_set_visibility(GTK_ENTRY(g_api_key_entry), FALSE);
    gtk_box_append(GTK_BOX(panel), g_api_key_entry);

    GtkWidget *prov_label = gtk_label_new("PROVEDOR");
    gtk_widget_add_css_class(prov_label, "config-label");
    gtk_label_set_xalign(GTK_LABEL(prov_label), 0.0f);
    gtk_box_append(GTK_BOX(panel), prov_label);

    const char *providers[] = {"openai", "anthropic", "google", "nvidia", "deepseek", "openrouter", nullptr};
    g_provider_drop = gtk_drop_down_new_from_strings(providers);
    gtk_box_append(GTK_BOX(panel), g_provider_drop);

    GtkWidget *model_label = gtk_label_new("MODELO");
    gtk_widget_add_css_class(model_label, "config-label");
    gtk_label_set_xalign(GTK_LABEL(model_label), 0.0f);
    gtk_box_append(GTK_BOX(panel), model_label);

    g_model_entry = gtk_entry_new();
    gtk_widget_add_css_class(g_model_entry, "config-entry");
    gtk_entry_set_placeholder_text(GTK_ENTRY(g_model_entry), "gpt-4o");
    gtk_box_append(GTK_BOX(panel), g_model_entry);

    GtkWidget *save_btn = gtk_button_new_with_label("Salvar");
    gtk_widget_add_css_class(save_btn, "btn-primary");
    gtk_widget_set_margin_top(save_btn, 12);
    g_signal_connect(save_btn, "clicked", G_CALLBACK(on_save_config), nullptr);
    gtk_box_append(GTK_BOX(panel), save_btn);

    gtk_box_append(GTK_BOX(parent), panel);
}

static void build_chat_area(GtkWidget *parent) {
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_hexpand(box, TRUE);

    GtkWidget *header = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    gtk_widget_add_css_class(header, "headerbar");
    gtk_widget_set_margin_top(header, 0);
    gtk_widget_set_margin_bottom(header, 0);
    gtk_widget_set_margin_start(header, 16);
    gtk_widget_set_margin_end(header, 16);

    GtkWidget *chat_title = gtk_label_new("Chat Principal");
    gtk_widget_add_css_class(chat_title, "title-label");
    gtk_box_append(GTK_BOX(header), chat_title);

    GtkWidget *spacer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_hexpand(spacer, TRUE);
    gtk_box_append(GTK_BOX(header), spacer);

    g_model_label = gtk_label_new("gpt-4o");
    gtk_widget_add_css_class(g_model_label, "model-badge");
    gtk_box_append(GTK_BOX(header), g_model_label);

    g_config_button = gtk_button_new_with_label("Config");
    gtk_widget_add_css_class(g_config_button, "btn-ghost");
    g_signal_connect(g_config_button, "clicked", G_CALLBACK(on_config_clicked), nullptr);
    gtk_box_append(GTK_BOX(header), g_config_button);

    gtk_box_append(GTK_BOX(box), header);

    GtkWidget *scroll = gtk_scrolled_window_new();
    gtk_widget_set_vexpand(scroll, TRUE);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll),
                                    GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_widget_add_css_class(scroll, "chat-area");

    g_chat_listbox = gtk_list_box_new();
    gtk_list_box_set_selection_mode(GTK_LIST_BOX(g_chat_listbox), GTK_SELECTION_NONE);
    gtk_widget_add_css_class(g_chat_listbox, "chat-area");
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll), g_chat_listbox);

    gtk_box_append(GTK_BOX(box), scroll);

    GtkWidget *input_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_widget_add_css_class(input_box, "input-area");
    gtk_widget_set_margin_top(input_box, 8);
    gtk_widget_set_margin_bottom(input_box, 8);
    gtk_widget_set_margin_start(input_box, 16);
    gtk_widget_set_margin_end(input_box, 16);

    GtkWidget *text_view = gtk_text_view_new();
    gtk_widget_add_css_class(text_view, "input-textview");
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(text_view), GTK_WRAP_WORD_CHAR);
    gtk_widget_set_size_request(text_view, -1, 80);
    g_input_buffer = gtk_text_view_get_buffer(GTK_TEXT_VIEW(text_view));

    GtkWidget *input_scroll = gtk_scrolled_window_new();
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(input_scroll), text_view);
    gtk_widget_set_hexpand(input_scroll, TRUE);
    gtk_box_append(GTK_BOX(input_box), input_scroll);

    GtkWidget *btn_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);

    g_send_button = gtk_button_new_with_label("Enviar");
    gtk_widget_add_css_class(g_send_button, "btn-primary");
    g_signal_connect(g_send_button, "clicked", G_CALLBACK(on_send_clicked), nullptr);

    g_stop_button = gtk_button_new_with_label("Parar");
    gtk_widget_add_css_class(g_stop_button, "btn-danger");
    gtk_widget_set_sensitive(g_stop_button, FALSE);
    g_signal_connect(g_stop_button, "clicked", G_CALLBACK(on_stop_clicked), nullptr);

    g_clear_button = gtk_button_new_with_label("Limpar");
    gtk_widget_add_css_class(g_clear_button, "btn-ghost");
    g_signal_connect(g_clear_button, "clicked", G_CALLBACK(on_clear_clicked), nullptr);

    gtk_box_append(GTK_BOX(btn_box), g_send_button);
    gtk_box_append(GTK_BOX(btn_box), g_stop_button);
    gtk_box_append(GTK_BOX(btn_box), g_clear_button);

    gtk_box_append(GTK_BOX(input_box), btn_box);
    gtk_box_append(GTK_BOX(box), input_box);

    GtkWidget *status_bar = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_widget_add_css_class(status_bar, "status-bar");

    GtkWidget *status_dot = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_add_css_class(status_dot, "status-dot");
    gtk_widget_add_css_class(status_dot, "status-online");

    g_status_label = gtk_label_new("Pronto");
    gtk_widget_add_css_class(g_status_label, "subtitle-label");

    gtk_box_append(GTK_BOX(status_bar), status_dot);
    gtk_box_append(GTK_BOX(status_bar), g_status_label);

    gtk_box_append(GTK_BOX(box), status_bar);

    gtk_box_append(GTK_BOX(parent), box);
}

static void activate(GtkApplication *app, gpointer) {
    g_main_window = adw_application_window_new(app);
    gtk_window_set_title(GTK_WINDOW(g_main_window), "Cassandra Agent");
    gtk_window_set_default_size(GTK_WINDOW(g_main_window), WINDOW_WIDTH, WINDOW_HEIGHT);
    gtk_window_set_resizable(GTK_WINDOW(g_main_window), TRUE);

    GtkWidget *main_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);

    build_sidebar(main_box);

    g_config_revealer = gtk_revealer_new();
    gtk_revealer_set_reveal_child(GTK_REVEALER(g_config_revealer), FALSE);
    gtk_revealer_set_transition_type(GTK_REVEALER(g_config_revealer), GTK_REVEALER_TRANSITION_TYPE_SLIDE_RIGHT);
    build_config_panel(g_config_revealer);
    gtk_box_append(GTK_BOX(main_box), g_config_revealer);

    build_chat_area(main_box);

    adw_application_window_set_content(ADW_APPLICATION_WINDOW(g_main_window), main_box);

    GtkCssProvider *provider = gtk_css_provider_new();
    gtk_css_provider_load_from_string(provider, CSS);
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(),
        GTK_STYLE_PROVIDER(provider),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION
    );

    g_timeout_add(50, drain_ui_queue, nullptr);

    gtk_widget_set_visible(g_main_window, TRUE);

    add_message("system", "Cassandra Agent inicializada. Digite sua mensagem abaixo.");
}

int main(int argc, char *argv[]) {
    adw_init();

    GtkApplication *app = gtk_application_new("com.cassandra.agent", G_APPLICATION_DEFAULT_FLAGS);
    g_signal_connect(app, "activate", G_CALLBACK(activate), nullptr);

    int status = g_application_run(G_APPLICATION(app), argc, argv);
    g_object_unref(app);
    return status;
}
