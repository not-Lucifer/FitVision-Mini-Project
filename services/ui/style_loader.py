import os
import streamlit as st
import streamlit.components.v1 as components
import base64
 

def load_css(file_path):
    if os.path.exists(file_path):
        with open(file_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def inject_local_font(font_path, font_name):
    if not os.path.exists(font_path):
        return
    
    with open(font_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    ext = os.path.splitext(font_path)[1].lstrip(".")
    fmt = {"otf": "opentype"}.get(ext, ext)
    mime = {"otf": "font/otf"}.get(ext, f"font/{ext}")

    st.markdown(f"""
        <style>
        @font-face {{
            font-family: '{font_name}';
            src: url('data:{mime};base64,{encoded}') format('{fmt}');
            font-weight: 100 900;
            font-style: normal;
        }}
        </style>
    """, unsafe_allow_html=True)

def inject_webrtc_styles():
    components.html(
        """
        <script>
        (function patchWebRTCStyles() {
            function injectIntoIframe(iframe) {
                try {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    if (!doc || !doc.head) return;
                    if (doc.head.querySelector('#webrtc-custom-styles')) return;
                    const style = doc.createElement('style');
                    style.id = 'webrtc-custom-styles';
                    style.textContent = `
                        @import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@500;600&display=swap');
                        video {
                            border-radius: 14px;
                        }
                        .MuiButtonBase-root,
                        .MuiButton-root,
                        .MuiButton-contained,
                        .MuiButton-text {
                            border-radius: 999px !important;
                            font-family: 'Instrument Sans', sans-serif !important;
                            font-weight: 600 !important;
                            letter-spacing: 0 !important;
                            text-transform: none !important;
                            padding: 6px 20px !important;
                        }
                    `;
                    doc.head.appendChild(style);
                } catch (e) {
                    console.warn('[patcher] could not inject:', e);
                }
            }

            function findAndPatch() {
                const parentDoc = window.parent.document;
                const iframes = parentDoc.querySelectorAll('iframe');
                iframes.forEach(iframe => {
                    if (iframe.src && iframe.src.includes('webrtc')) {
                        if (iframe.contentDocument && iframe.contentDocument.readyState === 'complete') {
                            injectIntoIframe(iframe);
                        } else {
                            iframe.addEventListener('load', () => injectIntoIframe(iframe));
                        }
                    }
                });
            }

            findAndPatch();
        })();
        </script>
        """,
        height=0,
    )
