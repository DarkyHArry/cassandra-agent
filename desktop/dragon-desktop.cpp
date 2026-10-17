#include <gtk/gtk.h>
#include <adwaita.h>
#include <curl/curl.h>
#include <string>
#include <thread>
#include <mutex>
#include <queue>
#include <functional>
#include <atomic>

static GtkWidget *chat_view, *input_view, *status_label, *send_button, *endpoint_entry, *context_label;
static std::mutex ui_mutex;
static std::queue<std::function<void()>> ui_jobs;
static std::atomic_bool busy{false};
static std::string json_escape(const std::string &s) {
  std::string out;
  for (unsigned char c : s) switch (c) {
    case '"': out += "\\\""; break; case '\\': out += "\\\\"; break;
    case '\n': out += "\\n"; break; case '\r': out += "\\r"; break; case '\t': out += "\\t"; break;
    default: if (c >= 0x20) out += static_cast<char>(c);
  }
  return out;
}
static void on_ui(std::function<void()> fn) {
  { std::lock_guard<std::mutex> lock(ui_mutex); ui_jobs.push(std::move(fn)); }
  g_main_context_invoke(nullptr, [](gpointer) -> gboolean {
    std::queue<std::function<void()>> jobs;
    { std::lock_guard<std::mutex> lock(ui_mutex); std::swap(jobs, ui_jobs); }
    while (!jobs.empty()) { jobs.front()(); jobs.pop(); }
    return G_SOURCE_REMOVE;
  }, nullptr);
}
static size_t collect_data(char *p, size_t size, size_t count, void *data) {
  static_cast<std::string*>(data)->append(p, size * count); return size * count;
}
static std::string endpoint_url() {
  const char *raw = gtk_editable_get_text(GTK_EDITABLE(endpoint_entry));
  std::string value = raw && *raw ? raw : "http://127.0.0.1:8080";
  while (!value.empty() && value.back() == '/') value.pop_back();
  return value;
}
static void add_message(const std::string &text, bool user) {
  GtkWidget *row = gtk_box_new(GTK_ORIENTATION_VERTICAL, 5);
  gtk_widget_set_margin_start(row, 16); gtk_widget_set_margin_end(row, 16);
  gtk_widget_set_margin_top(row, 7); gtk_widget_set_margin_bottom(row, 7);
  GtkWidget *label = gtk_label_new(text.c_str());
  gtk_label_set_wrap(GTK_LABEL(label), TRUE);
  gtk_label_set_wrap_mode(GTK_LABEL(label), PANGO_WRAP_WORD_CHAR);
  gtk_label_set_selectable(GTK_LABEL(label), TRUE);
  gtk_label_set_xalign(GTK_LABEL(label), 0); gtk_label_set_yalign(GTK_LABEL(label), 0);
  gtk_widget_set_hexpand(label, TRUE);
  gtk_widget_add_css_class(label, user ? "user-message" : "assistant-message");
  gtk_box_append(GTK_BOX(row), label); gtk_list_box_append(GTK_LIST_BOX(chat_view), row);
}
static void set_status(const std::string &s) { gtk_label_set_text(GTK_LABEL(status_label), s.c_str()); }
static void send_message() {
  bool expected = false;
  if (!busy.compare_exchange_strong(expected, true)) return;
  GtkTextBuffer *buffer = gtk_text_view_get_buffer(GTK_TEXT_VIEW(input_view));
  GtkTextIter start, end; gtk_text_buffer_get_bounds(buffer, &start, &end);
  gchar *raw = gtk_text_buffer_get_text(buffer, &start, &end, FALSE);
  std::string prompt = raw ? raw : ""; g_free(raw);
  if (prompt.find_first_not_of(" \t\r\n") == std::string::npos) { busy = false; return; }
  gtk_text_buffer_set_text(buffer, "", -1); add_message(prompt, true);
  gtk_widget_set_sensitive(send_button, FALSE); set_status("Cassandra está trabalhando…");
  const std::string api = endpoint_url();
  std::thread([prompt, api] {
    std::string response; long http_code = 0; CURL *curl = curl_easy_init();
    if (curl) {
      const std::string url = api + "/api/chat";
      const std::string payload = "{\"message\":\"" + json_escape(prompt) + "\",\"thinking\":false}";
      struct curl_slist *headers = nullptr; headers = curl_slist_append(headers, "Content-Type: application/json");
      curl_easy_setopt(curl, CURLOPT_URL, url.c_str()); curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
      curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload.c_str()); curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(payload.size()));
      curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, collect_data); curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
      curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L); curl_easy_setopt(curl, CURLOPT_TIMEOUT, 600L); curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
      CURLcode result = curl_easy_perform(curl); curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
      if (result != CURLE_OK) response = std::string("Conexão com Cassandra falhou: ") + curl_easy_strerror(result) + "\nVerifique o backend e o endpoint.";
      else if (http_code < 200 || http_code >= 300) response = "A API retornou HTTP " + std::to_string(http_code) + ". Verifique o log do backend.";
      curl_slist_free_all(headers); curl_easy_cleanup(curl);
    } else response = "Não foi possível inicializar libcurl.";
    if (response.empty()) response = "A API terminou sem retornar conteúdo.";
    on_ui([response] { add_message(response, false); busy = false; gtk_widget_set_sensitive(send_button, TRUE); set_status("Pronta"); });
  }).detach();
}
static void send_clicked(GtkButton*, gpointer) { send_message(); }
static gboolean input_key(GtkEventControllerKey*, guint keyval, guint, GdkModifierType state, gpointer) {
  if (keyval == GDK_KEY_Return && (state & GDK_CONTROL_MASK)) { send_message(); return TRUE; } return FALSE;
}
static gboolean refresh_status(gpointer) {
  const std::string api = endpoint_url();
  std::thread([api] {
    std::string body; long code = 0; CURL *c = curl_easy_init();
    if (c) {
      const std::string url = api + "/api/status";
      curl_easy_setopt(c, CURLOPT_URL, url.c_str()); curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, collect_data);
      curl_easy_setopt(c, CURLOPT_WRITEDATA, &body); curl_easy_setopt(c, CURLOPT_CONNECTTIMEOUT, 2L);
      curl_easy_setopt(c, CURLOPT_TIMEOUT, 3L); curl_easy_setopt(c, CURLOPT_NOSIGNAL, 1L);
      CURLcode rc = curl_easy_perform(c); curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &code);
      if (rc != CURLE_OK || code < 200 || code >= 300) body.clear();
      curl_easy_cleanup(c);
    }
    const bool connected = !body.empty();
    const bool shell = body.find("\"allow_shell\":true") != std::string::npos || body.find("\"allow_shell\": true") != std::string::npos;
    const bool creds = body.find("\"credentials\":0") == std::string::npos && body.find("\"credentials\": 0") == std::string::npos;
    const std::string info = connected ? std::string("Backend: conectado\nAutonomia de shell: ") + (shell ? "ATIVA" : "DESATIVADA") +
      "\nCredenciais API: " + (creds ? "configuradas" : "não configuradas") + "\nPlataforma: Linux x86_64"
      : "Backend: desconectado\nVerifique o processo Cassandra.";
    on_ui([info, connected, shell] { gtk_label_set_text(GTK_LABEL(context_label), info.c_str()); if (!busy) set_status(connected ? (shell ? "Conectada · autonomia ativa" : "Conectada · shell desativado") : "Backend desconectado"); });
  }).detach();
  return G_SOURCE_CONTINUE;
}
static const char *css = R"CSS(
window{background:#090b14;color:#edf0ff}.sidebar{background:#101321;border-right:1px solid #252943}
.brand{color:#c5a6ff;font-size:23px;font-weight:800;letter-spacing:3px}.muted{color:#929bbd}
.section-title{color:#f2efff;font-size:25px;font-weight:750}
.assistant-message{background:#191e31;color:#f0f1ff;padding:16px;border-radius:4px 14px 14px 14px}
.user-message{background:#282443;color:#f7f2ff;padding:16px;border-radius:14px 4px 14px 14px}
.entry-area{background:#141829;border:1px solid #8d72f9;border-radius:14px;padding:8px}
button.send{background:#9a7aff;color:#100d21;border-radius:12px;padding:12px 18px;font-weight:800}
button.send:disabled{opacity:.5}.status{color:#65dfa0;font-size:12px}
.context{background:#0e1220;border-left:1px solid #252943;padding:18px}
)CSS";
static void clear_chat(GtkButton*, gpointer) {
  if (busy) return;
  const std::string api = endpoint_url();
  GtkWidget *child = gtk_widget_get_first_child(chat_view);
  while (child) { GtkWidget *next = gtk_widget_get_next_sibling(child); gtk_list_box_remove(GTK_LIST_BOX(chat_view), child); child = next; }
  add_message("Conversa limpa. Pode enviar uma nova tarefa.", false);
  std::thread([api] {
    CURL *c = curl_easy_init();
    if (c) { const std::string url = api + "/api/clear"; curl_easy_setopt(c,CURLOPT_URL,url.c_str()); curl_easy_setopt(c,CURLOPT_POST,1L); curl_easy_setopt(c,CURLOPT_CONNECTTIMEOUT,3L); curl_easy_setopt(c,CURLOPT_TIMEOUT,5L); curl_easy_setopt(c,CURLOPT_NOSIGNAL,1L); curl_easy_perform(c); curl_easy_cleanup(c); }
  }).detach();
}
static void activate(GtkApplication *app, gpointer) {
  GtkWidget *window = adw_application_window_new(app); gtk_window_set_title(GTK_WINDOW(window), "Cassandra Security"); gtk_window_set_default_size(GTK_WINDOW(window), 1360, 820);
  GtkWidget *root = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
  GtkWidget *side = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12); gtk_widget_set_size_request(side, 220, -1); gtk_widget_add_css_class(side, "sidebar");
  gtk_widget_set_margin_top(side, 26); gtk_widget_set_margin_start(side, 16); gtk_widget_set_margin_end(side, 16); gtk_widget_set_margin_bottom(side, 20);
  GtkWidget *logo = gtk_image_new_from_file("assets/cassandra.svg"); gtk_image_set_pixel_size(GTK_IMAGE(logo), 82); gtk_box_append(GTK_BOX(side), logo);
  GtkWidget *brand = gtk_label_new("CASSANDRA"); gtk_widget_add_css_class(brand, "brand"); gtk_box_append(GTK_BOX(side), brand);
  GtkWidget *sub = gtk_label_new("SECURITY"); gtk_widget_add_css_class(sub, "muted"); gtk_box_append(GTK_BOX(side), sub);
  GtkWidget *spacer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0); gtk_widget_set_vexpand(spacer, TRUE); gtk_box_append(GTK_BOX(side), spacer);
  GtkWidget *session = gtk_label_new("●  Sessão local"); gtk_widget_add_css_class(session, "status"); gtk_label_set_xalign(GTK_LABEL(session), 0); gtk_box_append(GTK_BOX(side), session);
  gtk_box_append(GTK_BOX(root), side);
  GtkWidget *center = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12); gtk_widget_set_hexpand(center, TRUE);
  gtk_widget_set_margin_start(center, 22); gtk_widget_set_margin_end(center, 22); gtk_widget_set_margin_top(center, 22); gtk_widget_set_margin_bottom(center, 14);
  GtkWidget *head = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12); GtkWidget *titles = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
  GtkWidget *title = gtk_label_new("Sessão de trabalho"); gtk_label_set_xalign(GTK_LABEL(title), 0); gtk_widget_add_css_class(title, "section-title"); gtk_box_append(GTK_BOX(titles), title);
  GtkWidget *subtitle = gtk_label_new("Cassandra · agente autônomo"); gtk_label_set_xalign(GTK_LABEL(subtitle), 0); gtk_widget_add_css_class(subtitle, "muted"); gtk_box_append(GTK_BOX(titles), subtitle);
  gtk_box_append(GTK_BOX(head), titles); GtkWidget *clear = gtk_button_new_with_label("Limpar conversa"); g_signal_connect(clear, "clicked", G_CALLBACK(clear_chat), nullptr); gtk_widget_set_halign(clear, GTK_ALIGN_END); gtk_box_append(GTK_BOX(head), clear); gtk_box_append(GTK_BOX(center), head);
  GtkWidget *scroll = gtk_scrolled_window_new(); gtk_widget_set_vexpand(scroll, TRUE); chat_view = gtk_list_box_new(); gtk_list_box_set_selection_mode(GTK_LIST_BOX(chat_view), GTK_SELECTION_NONE);
  gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll), chat_view); gtk_box_append(GTK_BOX(center), scroll);
  add_message("Olá! Sou a Cassandra. Envie uma tarefa. Com o backend em modo autônomo, a Cassandra pode executar comandos e continuar o ciclo de trabalho definido no núcleo.", false);
  GtkWidget *inputrow = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10); gtk_widget_add_css_class(inputrow, "entry-area");
  input_view = gtk_text_view_new(); gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(input_view), GTK_WRAP_WORD_CHAR); gtk_widget_set_size_request(input_view, -1, 82); gtk_widget_set_hexpand(input_view, TRUE);
  gtk_text_view_set_top_margin(GTK_TEXT_VIEW(input_view), 10); gtk_text_view_set_left_margin(GTK_TEXT_VIEW(input_view), 10);
  GtkEventController *keys = gtk_event_controller_key_new(); g_signal_connect(keys, "key-pressed", G_CALLBACK(input_key), nullptr); gtk_widget_add_controller(input_view, keys); gtk_box_append(GTK_BOX(inputrow), input_view);
  send_button = gtk_button_new_with_label("➤ Enviar"); gtk_widget_add_css_class(send_button, "send"); g_signal_connect(send_button, "clicked", G_CALLBACK(send_clicked), nullptr); gtk_box_append(GTK_BOX(inputrow), send_button); gtk_box_append(GTK_BOX(center), inputrow);
  status_label = gtk_label_new("Verificando backend…"); gtk_label_set_xalign(GTK_LABEL(status_label), 0); gtk_widget_add_css_class(status_label, "muted"); gtk_box_append(GTK_BOX(center), status_label); gtk_box_append(GTK_BOX(root), center);
  GtkWidget *context = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12); gtk_widget_set_size_request(context, 245, -1); gtk_widget_add_css_class(context, "context");
  GtkWidget *ct = gtk_label_new("Estado do agente"); gtk_label_set_xalign(GTK_LABEL(ct), 0); gtk_widget_add_css_class(ct, "section-title"); gtk_box_append(GTK_BOX(context), ct);
  context_label = gtk_label_new("Consultando a API local…"); gtk_label_set_xalign(GTK_LABEL(context_label), 0); gtk_label_set_yalign(GTK_LABEL(context_label), 0); gtk_label_set_wrap(GTK_LABEL(context_label), TRUE); gtk_box_append(GTK_BOX(context), context_label);
  gtk_box_append(GTK_BOX(context), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL));
  GtkWidget *ep_label = gtk_label_new("ENDPOINT LOCAL"); gtk_label_set_xalign(GTK_LABEL(ep_label), 0); gtk_widget_add_css_class(ep_label, "muted"); gtk_box_append(GTK_BOX(context), ep_label);
  endpoint_entry = gtk_entry_new(); gtk_editable_set_text(GTK_EDITABLE(endpoint_entry), "http://127.0.0.1:8080"); gtk_box_append(GTK_BOX(context), endpoint_entry);
  GtkWidget *note = gtk_label_new("A autonomia executa comandos com as permissões do seu usuário Linux. Use apenas tarefas e projetos confiáveis."); gtk_label_set_wrap(GTK_LABEL(note), TRUE); gtk_label_set_xalign(GTK_LABEL(note), 0); gtk_widget_add_css_class(note, "muted"); gtk_box_append(GTK_BOX(context), note); gtk_box_append(GTK_BOX(root), context);
  adw_style_manager_set_color_scheme(adw_style_manager_get_default(), ADW_COLOR_SCHEME_FORCE_DARK);
  GtkCssProvider *provider = gtk_css_provider_new(); gtk_css_provider_load_from_data(provider, css, -1);
  gtk_style_context_add_provider_for_display(gdk_display_get_default(), GTK_STYLE_PROVIDER(provider), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
  adw_application_window_set_content(ADW_APPLICATION_WINDOW(window), root); gtk_window_present(GTK_WINDOW(window));
  g_timeout_add_seconds(5, refresh_status, nullptr); refresh_status(nullptr);
}
int main(int argc, char **argv) {
  curl_global_init(CURL_GLOBAL_DEFAULT); AdwApplication *app = adw_application_new("io.github.darkyharry.CassandraSecurity", G_APPLICATION_FLAGS_NONE);
  g_signal_connect(app, "activate", G_CALLBACK(activate), nullptr); int result = g_application_run(G_APPLICATION(app), argc, argv);
  g_object_unref(app); curl_global_cleanup(); return result;
}