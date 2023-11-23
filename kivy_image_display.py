import os
from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock

class ImageDisplayApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.originals_folder = 'web_output/originals'
        self.blackwhite_folder = 'web_output/blackwhite'
        self.layout = GridLayout(cols=3, spacing=10, padding=(10, 10))
        self.search_input = TextInput(hint_text="Enter datetime (YYYY-MM-DD_HH-MM-SS)", multiline=False,
                                        size_hint=(1, 0.05))

    def build(self):
        self.update_images()
        Clock.schedule_interval(lambda dt: self.update_images(), 15)  # Update images every 15 seconds
        layout = BoxLayout(orientation="vertical", spacing=10)
        layout.add_widget(self.search_input)
        layout.add_widget(self.layout)
        self.search_input.bind(on_text_validate=self.on_search)
        return layout

    def update_images(self):
        self.layout.clear_widgets()

        # Display original images
        for filename in os.listdir(self.originals_folder):
            img = AsyncImage(source=os.path.join(self.originals_folder, filename))
            img_data = filename.split('_')  # Extracting metadata from filename
            metadata = f"Date: {img_data[1][:10]}\nTime: {img_data[2][:8]}\nCamera: {img_data[0]}"
            self.add_image_widget(img, metadata)

        # Display black and white images
        for filename in os.listdir(self.blackwhite_folder):
            img = AsyncImage(source=os.path.join(self.blackwhite_folder, filename))
            img_data = filename.split('_')  # Extracting metadata from filename
            metadata = f"Date: {img_data[1][:10]}\nTime: {img_data[2][:8]}\nCamera: {img_data[0]}"
            self.add_image_widget(img, metadata)

    def add_image_widget(self, img, metadata):
        box = BoxLayout(orientation="vertical")
        box.add_widget(img)
        label = Label(text=metadata, size_hint_y=None, height=50, font_size=15)
        box.add_widget(label)
        img.bind(on_touch_down=self.on_image_click)
        self.layout.add_widget(box)

    def on_search(self, instance):
        search_datetime = self.search_input.text.strip()
        if not search_datetime:
            self.update_images()
            return

        self.layout.clear_widgets()

        # Display original images
        for filename in os.listdir(self.originals_folder):
            if filename.startswith(f'original_{search_datetime}'):
                img = AsyncImage(source=os.path.join(self.originals_folder, filename))
                img_data = filename.split('_')  # Extracting metadata from filename
                metadata = f"Date: {img_data[1][:10]}\nTime: {img_data[2][:8]}\nCamera: {img_data[0]}"
                self.add_image_widget(img, metadata)

        # Display black and white images
        for filename in os.listdir(self.blackwhite_folder):
            if filename.startswith(f'bw_{search_datetime}'):
                img = AsyncImage(source=os.path.join(self.blackwhite_folder, filename))
                img_data = filename.split('_')  # Extracting metadata from filename
                metadata = f"Date: {img_data[1][:10]}\nTime: {img_data[2][:8]}\nCamera: {img_data[0]}"
                self.add_image_widget(img, metadata)

    def on_image_click(self, instance, touch):
        if instance.collide_point(*touch.pos):
            instance.size_hint = (1, 1)

if __name__ == '__main__':
    ImageDisplayApp().run()
